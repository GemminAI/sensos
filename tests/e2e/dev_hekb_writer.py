"""Dev/test-only writer for hekb-vnext's `POST /experience`.

Not for production use. Reuses `hekb-vnext/tools/dev_audit_signer.py`'s own
P-256 keygen/sign technique directly (same `cryptography` calls, no
subprocess) so this test exercises the real `X-Audit-Signature` governance
gate end to end, not a bypass of it.

`sensos_core.context_lifecycle_engine.HekbClient` (the one verified CLE ->
hekb-vnext connection) deliberately has no write method — CLE has no
business producing audit signatures (see that module's own docstring).
This writer exists precisely for orchestration/E2E-test contexts that DO
hold that authority, and is kept out of any production gateway.

Boots hekb-vnext's real FastAPI app (`store_service.app`) in-process via
Starlette's `TestClient`, against a throwaway `HEKB_DATA_DIR` — no network
port, no persistent state, no shared process.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.testclient import TestClient

HEKB_VNEXT_ROOT = Path("/Users/tomonam3/GemminAI/hekb-vnext")


def _stub_broken_recalibrate_dependency() -> None:
    """`hekb-vnext/index/recalibrate.py` hard-codes
    `sys.path.insert(0, ".../Projects/sensos/experiments/EXP-BABY-MAC005")`
    and imports `mac005_quantizer` from there. That path was archived off
    this Mac (`Projects/sensos` commit `7e29fe5`: "moved to SSD1TB
    archive") and is not present, so `import store_service` fails before
    ever reaching `/experience` -- a pre-existing, unrelated break in
    hekb-vnext, not something this Phase 3 test causes.

    `store_service.py` imports `index.recalibrate` unconditionally at
    module load time even though this test never calls
    `/trajectories/recalibrate`, so the whole app import fails without
    this stub. Temporary workaround per explicit instruction (2026-09-17)
    -- restoring the real `mac005_quantizer.py` from the SSD1TB archive is
    separate, unrelated work, tracked outside this test.
    """
    import sys
    import types

    if "index.recalibrate" in sys.modules:
        return

    stub = types.ModuleType("index.recalibrate")

    def _unavailable(*_args: Any, **_kwargs: Any):
        raise NotImplementedError(
            "index.recalibrate is stubbed out in this test run — see "
            "dev_hekb_writer._stub_broken_recalibrate_dependency()"
        )

    stub.new_job_id = _unavailable
    stub.get_job = _unavailable
    stub.run_recalibration_job = _unavailable
    sys.modules["index.recalibrate"] = stub


@dataclass
class DevHekbWriter:
    """A throwaway P-256 keypair + bearer token + `TestClient`, bound to one
    fresh, temporary hekb-vnext data directory."""

    client: TestClient
    private_key: ec.EllipticCurvePrivateKey

    @classmethod
    def start(cls, data_dir: Path) -> DevHekbWriter:
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["HEKB_DATA_DIR"] = str(data_dir)

        private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = private_key.public_key().public_numbers()
        # Raw 65-byte X9.63 uncompressed point — the exact format
        # `HEKB_AUDIT_PUBLIC_KEY_PATH` accepts, matching dev_audit_signer.py's
        # own `keygen()`.
        raw_point = b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
        public_key_path = data_dir / "dev_public_key.raw"
        public_key_path.write_bytes(raw_point)
        os.environ["HEKB_AUDIT_PUBLIC_KEY_PATH"] = str(public_key_path)

        if str(HEKB_VNEXT_ROOT) not in sys.path:
            sys.path.insert(0, str(HEKB_VNEXT_ROOT))
        _stub_broken_recalibrate_dependency()
        import store_service  # noqa: E402 -- hekb-vnext's real FastAPI app

        token = secrets.token_hex(32)
        store_service._bearer_guard.token = token

        client = TestClient(store_service.app, headers={"Authorization": f"Bearer {token}"})
        return cls(client=client, private_key=private_key)

    def _sign(self, payload: dict[str, Any]) -> str:
        import store_service  # already on sys.path from start()

        message = store_service.canonical_bytes(payload)
        signature = self.private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        return base64.b64encode(signature).decode("ascii")

    def expected_object_id(self, payload: dict[str, Any]) -> str:
        """The real `MemoryObject`'s own SHA-256 computation — not a
        reimplementation — for the test to check the server's response
        against, independently of trusting the response body alone."""
        import store_service

        return store_service.MemoryObject(payload=payload).object_id

    def create_experience(self, payload: dict[str, Any], *, parent_id: str | None = None) -> dict[str, Any]:
        signature = self._sign(payload)
        response = self.client.post(
            "/experience",
            json={"payload": payload, "parent_id": parent_id},
            headers={"X-Audit-Signature": signature},
        )
        response.raise_for_status()
        return response.json()

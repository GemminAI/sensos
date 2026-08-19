#!/usr/bin/env python3
"""Regression check: no personal absolute filesystem path may enter a
dependency manifest that ships in this public repository.

Background (Publication Boundary Audit, Phase 3-E): services/nvs-runtime/
requirements.txt was found to contain two `-e /Users/<name>/GemminAI/...`
editable-install lines -- a machine-specific path that (a) leaks a
developer's local directory layout into a public file, and (b) makes the
file's own Docker build (services/nvs-runtime/Dockerfile: `COPY
requirements.txt` then `pip install -r requirements.txt`) silently
uninstallable in any container, since that host path does not exist in
the build context. This script catches a recurrence of either problem in
any `requirements*.txt` or `pyproject.toml` in the repository.

Stdlib only. No new dependencies. Exit 0 iff clean; prints every hit and
exits 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Matches absolute POSIX paths (/Users/..., /home/..., /root/...) or a
# Windows drive-letter absolute path -- deliberately broad, not just
# `/Users/`, since any absolute filesystem path in a manifest is the same
# class of problem regardless of whose machine it came from.
_ABSOLUTE_PATH_DEP = re.compile(
    r"^\s*-e\s+(/[A-Za-z0-9_./-]+|[A-Za-z]:\\\\[^\s]+)\s*$"
)
_SKIP_DIR_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__"}

_MANIFEST_GLOBS = ("requirements*.txt", "pyproject.toml")


def find_hits(root: Path) -> list[str]:
    hits: list[str] = []
    for pattern in _MANIFEST_GLOBS:
        for path in root.rglob(pattern):
            if any(part in _SKIP_DIR_PARTS for part in path.parts):
                continue
            # Never flag the safe, path-free .example templates themselves.
            if path.name.endswith(".example"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if _ABSOLUTE_PATH_DEP.match(line):
                    hits.append(f"{path}:{lineno}: {line.strip()}")
    return hits


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    hits = find_hits(root)
    if hits:
        print("Personal/absolute filesystem paths found in dependency manifests:")
        for h in hits:
            print(f"  {h}")
        print(
            "\nEditable local-repo dependencies must use a *.example template "
            "(see services/nvs-runtime/requirements-local.example) or a real "
            "package/index reference -- never a machine-specific absolute path "
            "committed to a tracked manifest."
        )
        return 1
    print("PERSONAL_PATH_CHECK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

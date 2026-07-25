import hashlib
import uuid
from datetime import datetime

from common.metadata import build_metadata


def test_build_metadata_shape():
    meta = build_metadata(text="The capital of Japan is Tokyo.", provider="anthropic", model="claude-haiku-4-5-20251001")
    assert uuid.UUID(meta["annotation_id"]).version == 4
    datetime.fromisoformat(meta["created_at"])  # raises if not ISO8601
    assert meta["schema_version"] == "1.0"
    assert meta["engine"] == "semantic-annotator"
    assert meta["provider"] == "anthropic"
    assert meta["model"] == "claude-haiku-4-5-20251001"
    assert meta["input_length"] == len("The capital of Japan is Tokyo.")


def test_build_metadata_annotation_id_is_not_a_hash_of_the_text():
    """Regression guard against the exact anti-pattern this codebase's
    predecessor (nvs-platform/kernel/observer/tag_extractor.py) used: never
    fill an identifier-shaped field with a hash of the input that looks
    like a real value but carries zero semantic content."""
    text = "The capital of Japan is Tokyo."
    meta = build_metadata(text=text, provider="anthropic", model="m")
    sha256_hex = hashlib.sha256(text.encode()).hexdigest()
    assert meta["annotation_id"] != sha256_hex
    assert sha256_hex[:8] not in meta["annotation_id"]


def test_build_metadata_ids_are_unique_per_call():
    meta_a = build_metadata(text="same text", provider="anthropic", model="m")
    meta_b = build_metadata(text="same text", provider="anthropic", model="m")
    assert meta_a["annotation_id"] != meta_b["annotation_id"]

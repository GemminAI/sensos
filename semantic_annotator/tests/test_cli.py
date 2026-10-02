import io
import json

from semantic_annotator.annotator import PassthroughAnnotator
from semantic_annotator.cli import run


def test_run_reads_ndjson_and_writes_annotated_ndjson() -> None:
    input_stream = io.StringIO(
        json.dumps(
            {
                "id": "obs-1",
                "source": "test-sensor",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "payload": {"text": "hello"},
            }
        )
        + "\n"
    )
    output_stream = io.StringIO()

    run(input_stream, output_stream, PassthroughAnnotator())

    lines = output_stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["observation"]["id"] == "obs-1"
    assert record["annotations"] == []


def test_run_skips_blank_lines() -> None:
    input_stream = io.StringIO("\n\n")
    output_stream = io.StringIO()

    run(input_stream, output_stream, PassthroughAnnotator())

    assert output_stream.getvalue() == ""

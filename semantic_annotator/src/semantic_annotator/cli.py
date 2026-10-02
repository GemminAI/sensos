"""Command-line entry point.

Reads newline-delimited JSON Observations and writes newline-delimited
JSON AnnotatedObservations. This is a thin adapter over
:mod:`semantic_annotator.pipeline`; it owns no annotation logic itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from datetime import datetime
from typing import TextIO

from semantic_annotator.annotator import Annotator, PassthroughAnnotator
from semantic_annotator.models import Observation
from semantic_annotator.pipeline import run_pipeline


def _parse_observations(lines: Iterable[str]) -> Iterator[Observation]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        yield Observation(
            id=raw["id"],
            source=raw["source"],
            timestamp=datetime.fromisoformat(raw["timestamp"]),
            payload=raw.get("payload", {}),
        )


def _serialize(obj: object) -> object:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="semantic-annotator",
        description=("Convert SensOS Reality observations into Annotated Observations."),
    )
    parser.add_argument(
        "-i",
        "--input",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="NDJSON file of Observations (default: stdin)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="NDJSON file to write AnnotatedObservations to (default: stdout)",
    )
    return parser


def run(input_stream: TextIO, output_stream: TextIO, annotator: Annotator) -> None:
    observations = _parse_observations(input_stream)
    for annotated in run_pipeline(observations, annotator):
        output_stream.write(json.dumps(asdict(annotated), default=_serialize))
        output_stream.write("\n")


def main() -> None:
    args = build_parser().parse_args()
    run(args.input, args.output, PassthroughAnnotator())

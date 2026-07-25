#!/usr/bin/env python3
"""Minimal Mock LLM HTTP server (stdlib only).

Not a Runtime. Used only for Phase 1 Observation Infrastructure smoke:
POST Hello → 200 + JSON with a response field.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("", "/health"):
            self._send_json(200, {"status": "ok", "service": "mock-llm"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}

        # Accept common prompt shapes; quality is not evaluated.
        prompt = (
            data.get("prompt")
            or data.get("message")
            or data.get("input")
            or ""
        )
        if isinstance(prompt, dict):
            prompt = prompt.get("content", "")

        self._send_json(
            200,
            {
                "response": f"mock:{prompt}" if prompt else "mock:ok",
                "model": "mock-llm",
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="EXP-5400B Phase 1 Mock LLM")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    server = HTTPServer((args.host, args.port), MockLLMHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()

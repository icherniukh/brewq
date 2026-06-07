#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PORT = 8765


def load_dashboard_module():
    path = ROOT / "scripts" / "update-status-dashboard.py"
    spec = importlib.util.spec_from_file_location("update_status_dashboard", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/status-dashboard"}:
            self.path = "/status-dashboard.html"
            return super().do_GET()
        if path == "/status-dashboard-data.json":
            return self.write_live_data()
        return super().do_GET()

    def write_live_data(self) -> None:
        data = load_dashboard_module().build_data()
        payload = json.dumps(data, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard: http://127.0.0.1:{PORT}/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

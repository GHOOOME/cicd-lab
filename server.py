import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit


VERSION = Path(__file__).with_name("VERSION").read_text().strip()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def do_GET(self):
        self.respond()

    def do_HEAD(self):
        self.respond(send_body=False)

    def respond(self, send_body=True):
        routes = {
            "/": {
                "service": "cicd-lab",
                "version": VERSION,
                "endpoints": ["/health", "/version"],
            },
            "/health": {"status": "ok", "version": VERSION},
            "/version": {"version": VERSION},
        }
        payload = routes.get(urlsplit(self.path).path)
        status = 200 if payload is not None else 404
        body = json.dumps(payload or {"error": "not_found"}, indent=2).encode() + b"\n"
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)


def create_server(host="127.0.0.1", port=18081):
    return HTTPServer((host, port), Handler)


if __name__ == "__main__":
    with create_server(
        os.environ.get("CICD_LAB_HOST", "127.0.0.1"),
        int(os.environ.get("CICD_LAB_PORT", "18081")),
    ) as server:
        print(f"cicd-lab {VERSION} listening on {server.server_address}", flush=True)
        server.serve_forever()

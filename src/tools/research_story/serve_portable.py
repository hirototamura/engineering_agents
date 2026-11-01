"""Serve only the two portable research-article HTML files on a private LAN."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit


PAGES = {"/index.html": "index.html", "/index.ja.html": "index.ja.html"}


def allowed_page(route: str) -> str | None:
    return PAGES.get(urlsplit(route).path)


def serve(directory: Path, host: str, port: int) -> None:
    address = ipaddress.ip_address(host)
    if address.version != 4 or address.is_unspecified or address.is_link_local or not address.is_private:
        raise ValueError("Bind to a specific private IPv4 address, not all interfaces or a public address")
    directory = directory.resolve()
    for filename in PAGES.values():
        file = directory / filename
        if not file.is_file() or not file.resolve().is_relative_to(directory):
            raise FileNotFoundError(f"Missing portable article: {file}")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _respond(self, send_body: bool) -> None:
            if urlsplit(self.path).path == "/":
                self.send_response(302)
                self.send_header("Location", "/index.html")
                self.end_headers()
                return
            filename = allowed_page(self.path)
            if filename is None:
                self.send_error(404)
                return
            content = (directory / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if send_body:
                self.wfile.write(content)

        def do_GET(self) -> None:
            self._respond(True)

        def do_HEAD(self) -> None:
            self._respond(False)

    with ThreadingHTTPServer((host, port), Handler) as server:
        print(f"English: http://{host}:{port}/index.html", flush=True)
        print(f"Japanese: http://{host}:{port}/index.ja.html", flush=True)
        print("Serving only these two HTML files. Press Control-C to stop.", flush=True)
        server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--host", required=True, help="this Mac's private Wi-Fi or Ethernet IPv4 address")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    serve(args.directory, args.host, args.port)


if __name__ == "__main__":
    main()

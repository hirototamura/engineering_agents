"""Serve the offline Isaac viewer and the restored archive on localhost."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC = Path(__file__).resolve().parents[1] / "public"


class OfflineViewerHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript"}

    def translate_path(self, path):
        url_path = urlsplit(path).path
        if url_path in ("/isaac/viewer", "/isaac/viewer/", "/isaac/viewer/index.html"):
            path = url_path.replace("/isaac/viewer", "/isaac-viewer", 1)
        return super().translate_path(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not (PUBLIC / "isaac/data/manifest.json").is_file():
        parser.error("Restore the Isaac archive with scripts/restore-isaac.mjs first.")

    handler = partial(OfflineViewerHandler, directory=str(PUBLIC))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Open http://127.0.0.1:{server.server_port}/isaac/viewer/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

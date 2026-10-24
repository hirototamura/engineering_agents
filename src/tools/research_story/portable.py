"""Export the bilingual research article as self-contained phone reading files.

Only the two HTML files are served to phones. Their figures, recorded poses,
charts, styles, scripts, and evidence JSON are embedded in each page.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path

from .build import HERE, render


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def portable_page(source: str) -> str:
    before_script, separator, after_script = source.partition('<script id="research-evidence"')
    if not separator:
        raise ValueError("Missing embedded evidence script")
    # The public article keeps research references and language navigation only.
    # It needs neither a workspace nor downloads from campaign archives.
    page = source
    links = _Links()
    links.feed(page)
    if any(not link.startswith(("#", "https://")) and link not in {"index.html", "index.ja.html"}
           for link in links.hrefs):
        raise ValueError("Portable article has an unbundled local link")
    if 'id="research-evidence"' not in page:
        raise ValueError("Portable article is missing embedded evidence")
    return page


def export(workspace: Path, output: Path) -> list[Path]:
    data = json.loads((HERE / "evidence.json").read_text(encoding="utf-8"))
    copy = json.loads((HERE / "copy.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for language, filename in (("en", "index.html"), ("ja", "index.ja.html")):
        path = output / filename
        page = render(data, copy, language, path, workspace)
        path.write_text(portable_page(page), encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    output = (args.output or workspace / "reports/iphone-research").expanduser().resolve()
    for path in export(workspace, output):
        print(path)


if __name__ == "__main__":
    main()

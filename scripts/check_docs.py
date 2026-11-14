"""Check the built reader journeys, local links, and documentation boundaries.

Run after ``mkdocs build --strict``. Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("scrubber_degradation", "ssos_eclss_loop", "balancing_cube")


class Page(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.feed(source)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        for name in ("href", "src"):
            if values.get(name):
                self.links.append(values[name])


def local_target(page: Path, link: str, site: Path):
    url = urlsplit(link)
    if url.scheme or url.netloc:
        return None
    path = unquote(url.path)
    target = (site / path.lstrip("/")) if path.startswith("/") else page.parent / path
    target = target.resolve() if path else page
    if target.is_dir():
        target /= "index.html"
    return target, unquote(url.fragment)


def check(site: Path) -> list[str]:
    errors: list[str] = []
    source_root = ROOT / "docs"
    mirrored: dict[str, set[str]] = {}
    legacy = re.compile(
        r"以前の見出しからの案内|Previous heading locations|"
        r"移転したドキュメント|^# Documentation moved", re.MULTILINE
    )
    for language in ("en", "ja"):
        locale_root = source_root / language
        mirrored[language] = set()
        for source in locale_root.rglob("*.md"):
            relative = source.relative_to(locale_root)
            if relative.as_posix() != "index.md" and relative.parts[0] not in {
                "users", "developers"
            }:
                errors.append(f"Outside reader sections: {source.relative_to(ROOT)}")
            mirrored[language].add(relative.as_posix())
            if legacy.search(source.read_text(encoding="utf-8")):
                errors.append(f"Obsolete navigation: {source.relative_to(ROOT)}")
    for relative in sorted(mirrored["en"] ^ mirrored["ja"]):
        errors.append(f"Missing language counterpart: {relative}")

    if not (site / "index.html").is_file():
        return errors + [f"No built documentation at {site}; run mkdocs build --strict"]
    for path in site.rglob("*"):
        if "_archive" in path.parts or "AGENTS" in path.parts:
            errors.append(f"Internal documentation published: {path.relative_to(site)}")
    pages = {
        path: Page(path.read_text(encoding="utf-8"))
        for path in site.rglob("*.html")
    }
    count = 0
    for path, page in pages.items():
        for link in page.links:
            resolved = local_target(path, link, site)
            if resolved is None:
                continue
            target, fragment = resolved
            count += 1
            if not target.is_relative_to(site) or not target.exists():
                errors.append(f"Broken target: {path.relative_to(site)} → {link}")
            elif fragment and target in pages and fragment not in pages[target].ids:
                errors.append(f"Broken anchor: {path.relative_to(site)} → {link}")

    for prefix, other in (("", "ja"), ("ja", "")):
        for audience in ("users", "developers"):
            landing = site / prefix / audience / "index.html"
            if landing not in pages:
                errors.append(f"Missing reader landing: {landing.relative_to(site)}")
                continue
            for scenario in SCENARIOS:
                parent = site / prefix / audience / "scenarios" / scenario / "index.html"
                if parent not in pages:
                    errors.append(f"Missing scenario parent: {parent.relative_to(site)}")
                    continue
                for name in (
                    ("configuration", "running", "results")
                    if audience == "users" else ("implementation", "evaluation")
                ):
                    destination = parent.parent / name / "index.html"
                    linked = {
                        value[0] for link in pages[parent].links
                        if (value := local_target(parent, link, site)) is not None
                    }
                    if destination not in linked:
                        errors.append(f"Unreachable {name}: {parent.relative_to(site)}")
            alternate = site / other / audience / "index.html"
            if not any(
                value[0] == alternate for link in pages[landing].links
                if (value := local_target(landing, link, site)) is not None
            ):
                errors.append(f"Missing language switch: {landing.relative_to(site)}")

    for index in site.rglob("search_index.json"):
        data = json.loads(index.read_text(encoding="utf-8"))
        for record in data.get("docs", []):
            location = unquote(record.get("location", ""))
            if "_archive" in location or re.search(r"(^|/)AGENTS(/|\.|$)", location):
                errors.append(f"Internal documentation indexed: {location}")
    print(f"Checked {len(pages)} built pages and {count} local links.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=ROOT / "site")
    errors = check(parser.parse_args().site_dir.resolve())
    if errors:
        print("\n".join(errors[:25]))
        print(f"Documentation checks failed: {len(errors)} issue(s).")
        return 1
    print("Reader sections, language pairs, links, and publication boundaries passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

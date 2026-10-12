#!/usr/bin/env python3
"""Check language pairs against unchanged source reports and numeric evidence."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re


from .paths import HERE, WORKSPACE
MANIFEST = HERE / "translation_manifest.json"
JSON_SCRIPT = re.compile(r"<script\b[^>]*\btype\s*=\s*['\"]application/json['\"][^>]*>(.*?)</script\s*>", re.I | re.S)


class NavigationLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        assert tag != "button", "Report navigation shall use native links"
        attributes = dict(attrs)
        assert "onclick" not in attributes, "Navigation shall not depend on inline handlers"
        if tag == "a":
            self.links.append(attributes["href"])


def numeric_digest(value) -> str:
    digest = hashlib.sha256()

    def walk(item, path):
        if isinstance(item, dict):
            for key in sorted(item):
                walk(item[key], path + (str(key),))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, path + (str(index),))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            digest.update(json.dumps([path, item], ensure_ascii=False, separators=(",", ":")).encode())

    walk(value, ())
    return digest.hexdigest()


def report_numbers(source: str) -> list[str]:
    digests = []
    for match in JSON_SCRIPT.findall(source):
        try:
            payload = json.loads(match)
        except ValueError:
            continue
        digests.append(numeric_digest(payload))
    return digests


def verify() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = manifest["entries"]
    assert rows, "empty translation manifest"
    checked_json = 0
    for name, record in rows.items():
        original = WORKSPACE / name
        source = original.read_text(encoding="utf-8")
        assert hashlib.sha256(source.encode()).hexdigest() == record["source_sha256"], name
        original_numbers = report_numbers(source)
        for language in ("en", "ja"):
            path = WORKSPACE / record[language]
            assert path.is_file(), path
            output = path.read_text(encoding="utf-8")
            assert re.search(rf"<html\b[^>]*\blang=['\"]{language}['\"]", output[:1000], re.I), path
            assert 'id="report-language-switch"' in output, path
            assert 'id="report-source-links"' in output, path
            toolbar = re.search(r'<div id="report-language-switch"\s.*?</div>', output, re.S)
            assert toolbar, path
            navigation = NavigationLinks()
            navigation.feed(toolbar.group())
            other = "ja" if language == "en" else "en"
            expected = [WORKSPACE / record[other], HERE / language / "index.html", original]
            assert len(navigation.links) == 3, path
            for href, target in zip(navigation.links, expected):
                assert (path.parent / href).resolve() == target.resolve(), (path, href)
                assert target.is_file(), target
            assert ".filter(node=>!node.closest('#report-language-switch'))" in output, path
            assert "__MAP__" not in output and "__SOURCE_DIR__" not in output, path
            assert report_numbers(output) == original_numbers, f"Numeric evidence changed: {path}"
            checked_json += len(original_numbers)
    print(f"Verified {len(rows)} report pairs ({len(rows)*2} HTML pages); {checked_json} JSON numeric evidence comparisons passed.")


if __name__ == "__main__":
    verify()

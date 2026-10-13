#!/usr/bin/env python3
"""Capture report pages with an isolated headless Chrome profile; cache WebP previews."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from PIL import Image

from . import catalog


from .paths import HERE, WORKSPACE
OUTPUT = HERE / "thumbnails"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
CAPTURE_VERSION = 1


def capture_page(page: Path | str, image: Path, timeout: float = 40,
                 viewport: tuple[int, int] = (1440, 900),
                 size: tuple[int, int] = (720, 450)) -> None:
    """Render the page itself, then reduce its viewport screenshot to 720 x 450."""
    chrome = str(CHROME) if CHROME.is_file() else shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        raise RuntimeError("Google Chrome or Chromium is required for page previews")
    image.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="engineering-report-capture-") as temporary:
        base = Path(temporary)
        screenshot = base / "viewport.png"
        command = [chrome, "--headless", "--disable-gpu", "--no-first-run",
                   "--no-default-browser-check", "--disable-background-networking",
                   "--disable-extensions", "--disable-sync", "--hide-scrollbars",
                   "--allow-file-access-from-files", "--force-device-scale-factor=1",
                   f"--user-data-dir={base / 'profile'}", f"--window-size={viewport[0]},{viewport[1]}",
                   "--virtual-time-budget=4000", f"--screenshot={screenshot}",
                   page.as_uri() if isinstance(page, Path) else page]
        with (base / "chrome.log").open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if screenshot.is_file():
                        try:
                            with Image.open(screenshot) as rendered:
                                rendered.load()
                                preview = rendered.convert("RGB")
                            break
                        except OSError:
                            pass
                    if process.poll() is not None:
                        raise RuntimeError("Chrome stopped before it wrote a screenshot")
                    time.sleep(0.15)
                else:
                    raise TimeoutError(f"No screenshot after {timeout:g} seconds")
            finally:
                # Only terminate this isolated capture process and its children.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        preview = preview.resize(size, Image.Resampling.LANCZOS)
        temporary_image = image.with_suffix(".tmp")
        preview.save(temporary_image, "WEBP", quality=82, method=6)
        os.replace(temporary_image, image)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    entries = catalog.build_catalog()["entries"]
    # All indexed entries have previews, including older versions in the All HTML view.
    pages = sorted({page for entry in entries for page in
                    (list(entry.get("localized", {}).values()) or [entry["path"]])})
    try:
        manifest = json.loads(catalog.THUMBNAILS.read_text())
    except (OSError, ValueError):
        manifest = {"schema_version": 1, "entries": {}}
    records = manifest["entries"]
    pending = []
    for relative in pages:
        page = WORKSPACE / relative
        stat = page.stat()
        record = records.get(relative, {})
        if (not args.force and record.get("capture_version") == CAPTURE_VERSION
                and record.get("source_modified_ns") == stat.st_mtime_ns
                and record.get("source_size_bytes") == stat.st_size
                and record.get("image") and (WORKSPACE / record["image"]).is_file()):
            continue
        pending.append((relative, stat))
    if args.limit is not None:
        pending = pending[:args.limit]
    print(f"{len(pages)} page previews; {len(pending)} need capture", flush=True)
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        tasks = {}
        for relative, stat in pending:
            name = hashlib.sha256(relative.encode()).hexdigest()[:20] + ".webp"
            image = OUTPUT / name
            tasks[pool.submit(capture_page, WORKSPACE / relative, image)] = (relative, stat, image)
        for number, task in enumerate(as_completed(tasks), 1):
            relative, stat, image = tasks[task]
            try:
                task.result()
                records[relative] = {"image": image.relative_to(WORKSPACE).as_posix(),
                                     "source_modified_ns": stat.st_mtime_ns,
                                     "source_size_bytes": stat.st_size,
                                     "capture_version": CAPTURE_VERSION,
                                     "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                     "viewport": [1440, 900], "size": [720, 450]}
            except Exception as error:
                failures.append(relative)
                print(f"Capture failed: {relative}: {error}", flush=True)
            if number % 10 == 0 or number == len(pending):
                catalog.atomic_write(catalog.THUMBNAILS, json.dumps(manifest, indent=2) + "\n")
                print(f"Captured {number}/{len(pending)} ({len(failures)} failures)", flush=True)
    catalog.atomic_write(catalog.THUMBNAILS, json.dumps(manifest, indent=2) + "\n")
    result = catalog.build_catalog()
    print(f"Catalog: {result['report_count']} latest reports; {result['all_html_count']} indexed files", flush=True)
    if failures:
        raise SystemExit(f"{len(failures)} preview captures failed; run again to retry")


if __name__ == "__main__":
    main()

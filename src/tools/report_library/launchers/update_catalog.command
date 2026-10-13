#!/bin/zsh
set -e
report_dir="$(cd "$(dirname "$0")" && pwd)"
python3 "$report_dir/catalog.py" build
python3 "$report_dir/capture_thumbnails.py"
open "$report_dir/index.html"

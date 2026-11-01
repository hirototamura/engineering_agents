#!/bin/zsh
set -e
report_dir="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$report_dir/catalog.py" serve --open

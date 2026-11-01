#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:18001/v1/models", timeout=2)' >/dev/null 2>&1; then
  echo "Connecting to the Qwen server. Connect the Mac VPN first if required."
  ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -L 18001:127.0.0.1:8001 one-piece@10.10.0.108 &
  tunnel_pid=$!
  trap 'kill "$tunnel_pid" 2>/dev/null || true' EXIT
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:18001/v1/models", timeout=2)' >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:18001/v1/models", timeout=2)' >/dev/null 2>&1; then
  echo "The Qwen endpoint is unavailable. Check the VPN and SSH access, then try again." >&2
  exit 1
fi

python3 reports/translate_reports.py
python3 reports/verify_translations.py
python3 reports/capture_thumbnails.py
python3 reports/catalog.py build
open reports/index.html

#!/bin/zsh
set -e
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
workspace="$(cd "$repo_dir/.." && pwd)"
python_bin="$workspace/.venv-integration/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin=python3
fi
lan_ip=""
for interface in en0 en1; do
  lan_ip="$(ifconfig "$interface" 2>/dev/null | awk '$1 == "inet" {print $2; exit}')"
  if [[ -n "$lan_ip" && "$lan_ip" != 169.254.* ]]; then
    break
  fi
  lan_ip=""
done
if [[ -z "$lan_ip" ]]; then
  echo "Connect this Mac and iPhone to the same Wi-Fi, then run this launcher again."
  exit 1
fi
PYTHONPATH="$repo_dir/src" "$python_bin" -m tools.research_story.portable --workspace "$workspace"
echo "Open the English or Japanese URL below on the iPhone."
echo "Keep this Terminal window open; Control-C stops sharing."
exec "$python_bin" "$repo_dir/src/tools/research_story/serve_portable.py" \
  --directory "$workspace/reports/iphone-research" --host "$lan_ip" --port 8766

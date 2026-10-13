"""Export the bilingual research article as self-contained phone reading files.

Only the two HTML files are served to phones. Their figures, saved CPU poses,
charts, styles, scripts, and evidence JSON are embedded in each page.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from .build import HERE, render


EA_PR = "https://github.com/hirototamura/engineering_agents/pull/82"
OP_PR = "https://github.com/hirototamura/one-piece/pull/12"
SIM_REPO = "https://github.com/hirototamura/balancing-cube-simulation"
RUN_RELEASE = "https://github.com/hirototamura/engineering_agents/releases/tag/reports-qwen-memory-20261012"


def _replace_link(match: re.Match[str]) -> str:
    link = match.group(1)
    if link.startswith(("#", "https://")) or link in {"index.html", "index.ja.html"}:
        return match.group(0)
    if link == "evidence.json":
        return 'href="#sources" id="download-evidence"'
    if "/reports/" in link or link.endswith(("/en/index.html", "/ja/index.html")):
        destination = EA_PR
    elif "/one-piece/" in link:
        destination = OP_PR
    elif "/balancing-cube-simulation/" in link:
        destination = SIM_REPO
    elif "pr82-onepiece-mujoco-loop" in link:
        destination = EA_PR
    else:
        raise ValueError(f"Unmapped local article link: {link}")
    return f'href="{destination}"'


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
    page = re.sub(r'href="([^"]+)"', _replace_link, before_script) + separator + after_script
    page = page.replace('data-ja="レポート一覧"', 'data-ja="ソースPR"')
    page = page.replace('>Report collection</a>', '>Source PR</a>')
    page = page.replace('data-ja="レポート一覧に戻る"', 'data-ja="Engineering Agents PR #82"')
    page = page.replace('>Return to the report collection</a>', '>Engineering Agents PR #82</a>')
    page = page.replace('data-ja="抽出した全根拠JSON"', 'data-ja="埋め込み根拠JSONをダウンロード"')
    page = page.replace('>Extracted evidence JSON</a>', '>Download embedded evidence JSON</a>')
    page = page.replace(
        'Local relative links assume the same workspace or restored artifact pack.',
        'This portable edition embeds the figure data. Full source files remain in the linked repositories and campaign archive.',
    )
    page = page.replace(
        '相対リンクは同じ作業領域または復元した成果パックを前提とします。',
        'この携帯版には図のデータを埋め込みました。元ファイルはリンク先のリポジトリとキャンペーンのアーカイブにあります。',
    )
    generated_links = r"(?m)^\$\('run-sources'\)\.innerHTML=.*$"
    replacement = ("$('run-sources').innerHTML=`<li><a href=\"" + RUN_RELEASE +
                   "\">${L('10- and 20-round Qwen campaign archives'," +
                   "'10反復・20反復Qwenキャンペーンのアーカイブ')}</a></li>`;")
    page, count = re.subn(generated_links, lambda _: replacement, page)
    if count != 1:
        raise ValueError("Expected one generated run-source link list")
    downloader = '''<script>
document.getElementById('download-evidence').addEventListener('click', event => {
  event.preventDefault();
  const content = document.getElementById('research-evidence').textContent;
  const url = URL.createObjectURL(new Blob([content], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'balancing-cube-research-evidence.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
</script>
'''
    page = page.replace('</body></html>', downloader + '</body></html>')
    links = _Links()
    links.feed(page)
    if any(not link.startswith(("#", "https://")) and link not in {"index.html", "index.ja.html"}
           for link in links.hrefs):
        raise ValueError("Portable article has an unbundled local link")
    if 'id="research-evidence"' not in page or 'id="download-evidence"' not in page:
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

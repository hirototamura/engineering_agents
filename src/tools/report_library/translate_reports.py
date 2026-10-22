#!/usr/bin/env python3
"""Build English/Japanese reading copies of the main local HTML reports.

The original reports remain untouched. Translations are presentation copies:
embedded numeric data, IDs, keys, code, and long raw evidence blocks are kept
as recorded. A Qwen OpenAI-compatible endpoint translates prose and labels.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import Request, urlopen

from . import catalog


from .paths import HERE, WORKSPACE
MANIFEST = HERE / "translation_manifest.json"
CACHE = HERE / "translation_cache.json"
MODEL = "qwen3.8-27b-uncensored"
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
ENGLISH_WORD = re.compile(r"[A-Za-z]{3,}")
HTML_TAG = re.compile(r"(<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>|<!--.*?-->|<[^>]+>)", re.I | re.S)
JSON_SCRIPT = re.compile(r"(<script\b[^>]*\btype\s*=\s*['\"]application/json['\"][^>]*>)(.*?)(</script\s*>)", re.I | re.S)
LANG_ATTR = re.compile(r"(<html\b[^>]*\blang\s*=\s*['\"])(?:ja|en)(['\"])", re.I)
TITLE_TAG = re.compile(r"(<title\b[^>]*>)(.*?)(</title\s*>)", re.I | re.S)
DISPLAY_ATTR = re.compile(r"\b(title|aria-label|placeholder|alt)=([\"'])(.*?)\2", re.I | re.S)
SKIP_TAGS = {"pre", "code", "kbd", "samp", "textarea"}
JAPANESE_FRAGMENT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff][\u3040-\u30ff\u3400-\u9fff\u3000-\u303fー・（）「」『』％%0-9A-Za-z .,:;!?+\-/]*")


def source_language(source: str) -> str:
    match = re.search(r"<html\b[^>]*\blang\s*=\s*['\"](ja|en)", source[:1000], re.I)
    return match.group(1).lower() if match else "ja" if JAPANESE.search(source[:2000]) else "en"


def is_prose(value: str, source_lang: str) -> bool:
    value = html.unescape(value.strip())
    if not value or len(value) > 1000:
        return False
    if source_lang == "ja":
        return bool(JAPANESE.search(value))
    if not ENGLISH_WORD.search(value):
        return False
    if re.fullmatch(r"[\w.\-/:+#%()]+", value) and (
        len(value) < 3 or value.isupper() or bool(re.search(r"[\d_./:+#%()]", value))
    ):
        return False
    # An ID, path, JSON fragment, formula, or URL is not report prose.
    if value.startswith(("http://", "https://", "{", "[", "<", "data:")):
        return False
    if re.search(r"[/\\][\w.\-/]+|\b(?:sha256|[a-f0-9]{32,})\b", value, re.I):
        return False
    return True


def text_nodes(source: str, source_lang: str) -> set[str]:
    words: set[str] = set()
    skip: list[str] = []
    for part in HTML_TAG.split(source):
        if not part:
            continue
        if part.startswith("<"):
            if part.lower().startswith(("<script", "<style", "<!--")):
                continue
            end = re.match(r"</([\w:-]+)", part)
            start = re.match(r"<([\w:-]+)", part)
            if end and skip and end.group(1).lower() == skip[-1]:
                skip.pop()
            elif start and start.group(1).lower() in SKIP_TAGS and not part.endswith("/>"):
                skip.append(start.group(1).lower())
            if start:
                for attr in DISPLAY_ATTR.finditer(part):
                    value = html.unescape(attr.group(3))
                    if is_prose(value, source_lang):
                        words.add(value.strip())
        elif not skip:
            value = html.unescape(part).strip()
            if is_prose(value, source_lang):
                words.add(value)
    return words


def json_values(source: str, source_lang: str) -> set[str]:
    words: set[str] = set()
    for match in JSON_SCRIPT.finditer(source):
        try:
            payload = json.loads(match.group(2))
        except ValueError:
            continue
        def visit(value):
            if isinstance(value, str) and is_prose(value, source_lang):
                words.add(value.strip())
            elif isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(payload)
    return words


def script_fragments(source: str, source_lang: str) -> set[str]:
    """Collect labels assembled by JavaScript without changing executable code."""
    if source_lang != "ja":
        return set()
    words = set()
    for match in re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>", source, re.I | re.S):
        if "application/json" in match.group(1):
            continue
        for fragment in JAPANESE_FRAGMENT.findall(match.group(2)):
            value = fragment.strip(" .,:;!?+-/ ")
            if value and len(value) < 300:
                words.add(value)
    return words


def load_cache() -> dict[str, dict[str, str]]:
    try:
        result = json.loads(CACHE.read_text(encoding="utf-8"))
        return {"ja_en": result.get("ja_en", {}), "en_ja": result.get("en_ja", {})}
    except (OSError, ValueError):
        return {"ja_en": {}, "en_ja": {}}


def save_cache(cache: dict) -> None:
    catalog.atomic_write(CACHE, json.dumps(cache, ensure_ascii=False, indent=2) + "\n")


def translate_batch(values: list[str], source_lang: str, endpoint: str) -> list[str]:
    target_lang = "English" if source_lang == "ja" else "Japanese"
    system = (
        f"You translate engineering report user-interface text from {'Japanese' if source_lang == 'ja' else 'English'} "
        f"to {target_lang}. Return ONLY a JSON object with keys 0 through {len(values)-1}, each value a translated string. "
        "Keep technical meaning, requirement modality (shall), numbers, units, equations, symbols, "
        "configuration IDs, model names and status codes unchanged. Use concise natural technical language. "
        "Do not add explanations. Translate every item; do not omit or merge entries."
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({str(i): text for i, text in enumerate(values)}, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 4096,
        "chat_template_kwargs": {"enable_thinking": False},
    }, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint.rstrip("/") + "/v1/chat/completions", data=body,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=120) as response:
        reply = json.load(response)["choices"][0]["message"]["content"]
    if reply.startswith("```"):
        reply = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    data = json.loads(reply)
    if not isinstance(data, dict) or set(data) != {str(i) for i in range(len(values))}:
        raise ValueError("Translator returned missing or extra translation keys")
    translated = [data[str(i)] for i in range(len(values))]
    if not all(isinstance(item, str) and item.strip() for item in translated):
        raise ValueError("Translator returned an empty or non-string item")
    return translated


def fill_translations(values: set[str], source_lang: str, cache: dict, endpoint: str, workers: int) -> None:
    slot = "ja_en" if source_lang == "ja" else "en_ja"
    missing = sorted(values - cache[slot].keys(), key=lambda item: (len(item), item))
    batches = []
    batch, characters = [], 0
    for value in missing:
        if batch and (len(batch) >= 25 or characters + len(value) > 3000):
            batches.append(batch)
            batch, characters = [], 0
        batch.append(value)
        characters += len(value)
    if batch:
        batches.append(batch)
    print(f"{slot}: {len(missing)} new strings in {len(batches)} batches", flush=True)

    def attempt(chunk: list[str]):
        for retry in range(3):
            try:
                return translate_batch(chunk, source_lang, endpoint)
            except Exception as error:
                if retry == 2:
                    if len(chunk) > 1:
                        midpoint = len(chunk) // 2
                        return attempt(chunk[:midpoint]) + attempt(chunk[midpoint:])
                    raise RuntimeError(f"Translation failed for {chunk[0][:80]!r}") from error
                time.sleep(1 + retry)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(attempt, chunk): chunk for chunk in batches}
        for number, future in enumerate(as_completed(futures), 1):
            chunk = futures[future]
            cache[slot].update(zip(chunk, future.result()))
            save_cache(cache)
            if number % 10 == 0 or number == len(batches):
                print(f"  {slot}: {number}/{len(batches)} batches", flush=True)


def replace_text(source: str, source_lang: str, translations: dict[str, str]) -> str:
    skip: list[str] = []
    output: list[str] = []
    for part in HTML_TAG.split(source):
        if not part:
            continue
        if part.startswith("<"):
            if part.lower().startswith(("<script", "<style", "<!--")):
                output.append(part)
                continue
            end = re.match(r"</([\w:-]+)", part)
            start = re.match(r"<([\w:-]+)", part)
            if end and skip and end.group(1).lower() == skip[-1]:
                skip.pop()
            elif start and start.group(1).lower() in SKIP_TAGS and not part.endswith("/>"):
                skip.append(start.group(1).lower())
            if start:
                def attr_sub(match):
                    value = html.unescape(match.group(3))
                    translated = translations.get(value.strip())
                    return (f"{match.group(1)}={match.group(2)}"
                            f"{html.escape(translated, quote=True) if translated else match.group(3)}{match.group(2)}")
                part = DISPLAY_ATTR.sub(attr_sub, part)
            output.append(part)
        elif skip:
            output.append(part)
        else:
            stripped = html.unescape(part).strip()
            translated = translations.get(stripped)
            if translated:
                leading = re.match(r"\s*", part).group(0)
                trailing = re.search(r"\s*$", part).group(0)
                output.append(leading + html.escape(translated, quote=False) + trailing)
            else:
                output.append(part)
    return "".join(output)


def replace_json(source: str, source_lang: str, translations: dict[str, str]) -> str:
    def json_sub(match):
        try:
            payload = json.loads(match.group(2))
        except ValueError:
            return match.group(0)
        def visit(value):
            if isinstance(value, str):
                return translations.get(value.strip(), value) if is_prose(value, source_lang) else value
            if isinstance(value, dict):
                return {key: visit(child) for key, child in value.items()}
            if isinstance(value, list):
                return [visit(child) for child in value]
            return value
        result = json.dumps(visit(payload), ensure_ascii=False, separators=(",", ":"))
        result = result.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        return match.group(1) + result + match.group(3)
    return JSON_SCRIPT.sub(json_sub, source)


def report_filename(path: str) -> str:
    digest = hashlib.sha256(path.encode()).hexdigest()[:12]
    stem = re.sub(r"[^a-z0-9]+", "-", Path(path).stem.lower()).strip("-")[:35]
    return f"{stem}-{digest}.html"


def native_counterpart(original: Path, language: str) -> Path | None:
    relative = original.relative_to(WORKSPACE).as_posix()
    pair = None
    if original.name == "bottom-corner-trial-report.html" and language == "ja":
        pair = original.with_name("bottom-corner-trial-report.ja.html")
    elif original.name == "bottom-corner-trial-report.ja.html" and language == "en":
        pair = original.with_name("bottom-corner-trial-report.html")
    elif original.name == "workflow-study-report.html" and language == "ja":
        pair = original.with_name("workflow-study-report.ja.html")
    elif original.name == "workflow-study-report.ja.html" and language == "en":
        pair = original.with_name("workflow-study-report.html")
    elif relative.endswith("/design_loop_analysis.html") and language == "ja":
        pair = original.with_name("design_loop_analysis.ja.html")
    elif relative.endswith("/design_loop_analysis.ja.html") and language == "en":
        pair = original.with_name("design_loop_analysis.html")
    elif "/docs/en/evaluation-scorecard-a3.html" in relative and language == "ja":
        pair = Path(str(original).replace("/docs/en/", "/docs/ja/"))
    elif "/docs/ja/evaluation-scorecard-a3.html" in relative and language == "en":
        pair = Path(str(original).replace("/docs/ja/", "/docs/en/"))
    return pair if pair and pair.is_file() else None


def navigation_toolbar(original: Path, destination: Path, language: str) -> str:
    original_relative = os.path.relpath(original, destination.parent).replace(os.sep, "/")
    other = "ja" if language == "en" else "en"
    common = 'text-decoration:none;display:inline-block;cursor:pointer;font:inherit;'
    return (
        '<div id="report-language-switch" role="navigation" aria-label="Report navigation" '
        'style="position:fixed;right:16px;bottom:16px;z-index:2147483647;'
        'display:flex;gap:6px;align-items:center;padding:7px 8px;background:#123c53;color:white;'
        'border:1px solid #9dbcc5;border-radius:9px;box-shadow:0 8px 30px #0004;'
        'font:600 13px/1.3 system-ui,sans-serif">'
        '<span style="padding:0 5px">Language / 言語</span>'
        f'<a href="../../{other}/items/{destination.name}" '
        f'aria-label="Switch to {"Japanese" if other == "ja" else "English"}" '
        f'style="{common}border:0;border-radius:5px;background:#fff;color:#123c53;padding:7px 10px">'
        f'{"日本語" if other == "ja" else "English"}</a>'
        '<a href="../index.html" aria-label="Report library" title="Report library / レポート一覧" '
        f'style="{common}border:1px solid #b7d2d9;border-radius:5px;background:transparent;color:white;padding:7px 10px">↩</a>'
        f'<a href="{html.escape(original_relative, quote=True)}" '
        'title="Original source / 原本" aria-label="Original source" '
        f'style="{common}border:1px solid #b7d2d9;border-radius:5px;background:transparent;color:white;padding:7px 10px">'
        'Source</a></div>'
    )


def reading_copy(source: str, original: Path, destination: Path, language: str,
                 translations: dict[str, str], original_lang: str,
                 relative_base: Path | None = None) -> str:
    if language != original_lang:
        source = replace_text(source, original_lang, translations)
        source = replace_json(source, original_lang, translations)
    source = LANG_ATTR.sub(lambda match: match.group(1) + language + match.group(2), source, count=1)
    if not re.search(r"<html\b[^>]*\blang=", source[:1000], re.I):
        source = re.sub(r"<html\b", f'<html lang="{language}"', source, count=1, flags=re.I)
    source_dir_relative = os.path.relpath(relative_base or original.parent, destination.parent).replace(os.sep, "/") + "/"
    button = navigation_toolbar(original, destination, language)
    if language == "en" and original_lang == "ja":
        mapping = {key: translations[key] for key in script_fragments(source, "ja") if key in translations}
        encoded = json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))
        encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        overlay = r'''<script id="report-dynamic-translation">
        (()=>{const M=__MAP__;const keys=Object.keys(M).sort((a,b)=>b.length-a.length);
        if(!keys.length)return;const escapeRe=x=>x.split('').map(c=>'\\^$.*+?()[]{}|'.includes(c)?'\\'+c:c).join('');
        const re=new RegExp(keys.map(escapeRe).join('|'),'g');
        const change=s=>s.replace(re,x=>M[x]);
        function scan(root){if(root.nodeType===3){if(!root.parentElement?.closest('#report-language-switch')&&/[\u3040-\u30ff\u3400-\u9fff]/.test(root.data))root.data=change(root.data);return;}
          if(root.nodeType!==1||root.closest('script,style,pre,code,#report-language-switch'))return;
          for(const attr of ['title','aria-label','placeholder']){const v=root.getAttribute(attr);if(v&&/[\u3040-\u30ff\u3400-\u9fff]/.test(v))root.setAttribute(attr,change(v));}
          const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT);while(walker.nextNode()){const n=walker.currentNode;
            if(n.nodeType===3){if(!n.parentElement?.closest('script,style,pre,code,#report-language-switch')&&/[\u3040-\u30ff\u3400-\u9fff]/.test(n.data))n.data=change(n.data);}
            else if(!n.closest('#report-language-switch'))for(const attr of ['title','aria-label','placeholder']){const v=n.getAttribute(attr);if(v&&/[\u3040-\u30ff\u3400-\u9fff]/.test(v))n.setAttribute(attr,change(v));}
          }
        }
        scan(document.body);new MutationObserver(records=>{for(const r of records){if(r.type==='characterData')scan(r.target);
          else if(r.type==='attributes')scan(r.target);else for(const n of r.addedNodes)scan(n);}})
          .observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder']});
        })();</script>'''
        button += overlay.replace("__MAP__", encoded)
    link_repair = r'''<script id="report-source-links">
      (()=>{const originalBase=new URL(__SOURCE_DIR__,location.href);
        const isRelative=v=>v&&!v.startsWith('#')&&!v.startsWith('//')&&!/^[a-z][a-z\d+.-]*:/i.test(v)&&!v.startsWith('/')&&!v.includes('${');
        function repair(root){if(root.nodeType!==1||root.closest('#report-language-switch,script,style'))return;
          const nodes=[root,...root.querySelectorAll('[href],[src],[poster],[data],[xlink\\:href]')]
            .filter(node=>!node.closest('#report-language-switch'));
          for(const node of nodes)for(const attr of ['href','src','poster','data','xlink:href']){
            const v=node.getAttribute(attr);if(isRelative(v))node.setAttribute(attr,new URL(v,originalBase).href);
          }
        }
        repair(document.body);new MutationObserver(records=>{for(const record of records){
          if(record.type==='attributes')repair(record.target);else for(const node of record.addedNodes)repair(node);
        }}).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['href','src','poster','data','xlink:href']});
      })();</script>'''
    button += link_repair.replace("__SOURCE_DIR__", json.dumps(source_dir_relative))
    if re.search(r"</body\s*>", source, re.I):
        source = re.sub(r"</body\s*>", lambda _match: button + "</body>", source, count=1, flags=re.I)
    else:
        source = re.sub(r"</html\s*>", lambda _match: button + "</body></html>", source,
                        count=1, flags=re.I)
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18001")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent model requests (default: 4)")
    parser.add_argument("--prepare-only", action="store_true", help="Count text without contacting the model")
    args = parser.parse_args()
    sources = [entry for entry in catalog.build_catalog()["entries"] if entry["scope"] == "report"]
    source_map = {}
    need = defaultdict(set)
    for entry in sources:
        source = (WORKSPACE / entry["path"]).read_text(encoding="utf-8", errors="replace")
        lang = source_language(source)
        source_map[entry["path"]] = (source, lang)
        need[lang].update(text_nodes(source, lang))
        need[lang].update(json_values(source, lang))
        need[lang].update(script_fragments(source, lang))
    print(f"{len(sources)} reports; Japanese strings: {len(need['ja'])}; English strings: {len(need['en'])}", flush=True)
    if args.prepare_only:
        return
    cache = load_cache()
    for language in ("ja", "en"):
        fill_translations(need[language], language, cache, args.endpoint, args.workers)
    manifest = {"schema_version": 1, "translator": MODEL, "entries": {}}
    for number, entry in enumerate(sources, 1):
        path = entry["path"]
        original = WORKSPACE / path
        source, lang = source_map[path]
        name = report_filename(path)
        paths = {}
        reading_sources = {}
        for language in ("en", "ja"):
            destination = HERE / language / "items" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            native = native_counterpart(original, language) if language != lang else None
            if native:
                content = reading_copy(native.read_text(encoding="utf-8"), original, destination,
                                       language, {}, language, relative_base=native.parent)
                reading_sources[language] = native.relative_to(WORKSPACE).as_posix()
            elif language == "ja" and lang == "en" and original.name == "memory-pipeline-report.html":
                from tools.build_cube_memory_report import build_report
                build_report(original.parent, destination)
                japanese_source = destination.read_text(encoding="utf-8")
                content = reading_copy(japanese_source, original, destination, "ja", {}, "ja",
                                       relative_base=destination.parent)
                reading_sources[language] = "engineering_agents/src/tools/build_cube_memory_report.py"
            else:
                slot = "ja_en" if lang == "ja" else "en_ja"
                content = reading_copy(source, original, destination, language, cache[slot], lang)
                reading_sources[language] = path
            catalog.atomic_write(destination, content)
            paths[language] = destination.relative_to(WORKSPACE).as_posix()
        manifest["entries"][path] = {"source_language": lang,
                                    "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                                    "en": paths["en"], "ja": paths["ja"],
                                    "reading_sources": reading_sources}
        print(f"[{number:02}/{len(sources)}] {path}", flush=True)
    catalog.atomic_write(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Translation manifest: {MANIFEST}", flush=True)


if __name__ == "__main__":
    main()

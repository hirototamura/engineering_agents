"""Preflight checks for the remote (VPN-reachable) GPU LLM endpoint.

Phase 0-B of the ECLSS Recursive Subsystem Engineering Agents design: before any
Engineering Agent code is written, confirm *empirically* what the GPU server
speaks. Nothing about the provider is assumed — the probe asks the endpoint.

Checks (design doc section 29):
  1. Python version
  2. host reachability (ICMP; informational only, many hosts drop ping)
  3. TCP connect to each candidate port
  4. LLM health API — ``GET /v1/models`` (OpenAI-compatible) and
     ``GET /api/tags`` (Ollama); whichever answers determines the provider
  5. structured JSON generation — the model must return ``{"ok": true}``
  6. parallel generation smoke — N concurrent requests, latency + failure rate

Endpoint configuration comes from the environment only; no private address or
token is stored in the repository (design doc section 73)::

    $env:EA_LLM_BASE_URL = "http://<private-host>:<port>"   # or .../v1
    $env:EA_LLM_MODEL    = "<served model id>"              # optional
    $env:EA_LLM_API_KEY  = "<token>"                        # optional

Alternatively pass ``--host`` and let the probe scan ``--ports``.

The report is written as JSON. Endpoint host/port are recorded (they are needed
to reproduce the result); API keys never are.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_PORTS = (8000, 8001, 11434)
DEFAULT_TIMEOUT_S = 30.0
HEALTH_TIMEOUT_S = 10.0
TCP_TIMEOUT_S = 3.0

BASE_URL_ENV = "EA_LLM_BASE_URL"
MODEL_ENV = "EA_LLM_MODEL"
API_KEY_ENV = "EA_LLM_API_KEY"

JSON_PROBE_PROMPT = (
    'Reply with exactly this JSON object and nothing else: {"ok": true}'
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _split_base_url(url: str) -> Tuple[str, Optional[int]]:
    """Return (host, port) from an http(s) URL without pulling in urllib3 parsing."""
    cleaned = url.strip().rstrip("/")
    for prefix in ("http://", "https://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    authority = cleaned.split("/", 1)[0]
    if ":" in authority:
        host, _, port_raw = authority.rpartition(":")
        try:
            return host, int(port_raw)
        except ValueError:
            return authority, None
    return authority, None


def _root_of(base_url: str) -> str:
    """Strip a trailing ``/v1`` so both API families can be probed."""
    cleaned = base_url.strip().rstrip("/")
    if cleaned.endswith("/v1"):
        return cleaned[: -len("/v1")]
    return cleaned


def _auth_headers(api_key: Optional[str]) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _redact(value: Optional[str]) -> str:
    if not value:
        return "(unset)"
    return f"(set, {len(value)} chars)"


# --------------------------------------------------------------------------- #
# check 1 — python
# --------------------------------------------------------------------------- #
def check_python() -> Dict[str, Any]:
    return {
        "ok": sys.version_info >= (3, 11),
        "version": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "requires": ">=3.11",
    }


# --------------------------------------------------------------------------- #
# check 2 — ICMP (informational)
# --------------------------------------------------------------------------- #
def check_ping(host: str) -> Dict[str, Any]:
    count_flag = "-n" if os.name == "nt" else "-c"
    try:
        completed = subprocess.run(
            ["ping", count_flag, "1", host],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "ok": completed.returncode == 0,
            "host": host,
            "returncode": completed.returncode,
            "note": "informational — hosts commonly drop ICMP even when the API is up",
        }
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"ok": False, "host": host, "error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# check 3 — TCP
# --------------------------------------------------------------------------- #
def check_tcp(host: str, ports: Tuple[int, ...]) -> Dict[str, Any]:
    results = []
    for port in ports:
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=TCP_TIMEOUT_S):
                results.append(
                    {
                        "port": port,
                        "open": True,
                        "connect_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                )
        except Exception as exc:
            results.append(
                {"port": port, "open": False, "error": f"{type(exc).__name__}: {exc}"}
            )
    return {"ok": any(r["open"] for r in results), "host": host, "ports": results}


# --------------------------------------------------------------------------- #
# check 4 — health / provider detection
# --------------------------------------------------------------------------- #
def check_health(root: str, api_key: Optional[str]) -> Dict[str, Any]:
    """Probe both API families; the one that answers identifies the provider."""
    probes: List[Dict[str, Any]] = []
    provider: Optional[str] = None
    models: List[str] = []
    api_base: Optional[str] = None

    candidates = (
        ("openai_compatible", f"{root}/v1/models", "data"),
        ("ollama", f"{root}/api/tags", "models"),
    )
    for name, url, payload_key in candidates:
        started = time.perf_counter()
        try:
            response = requests.get(
                url, headers=_auth_headers(api_key), timeout=HEALTH_TIMEOUT_S
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            entry: Dict[str, Any] = {
                "provider_candidate": name,
                "url": url,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
            }
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                items = payload.get(payload_key) or []
                found = [
                    str(item.get("id") or item.get("name") or item)
                    for item in items
                    if isinstance(item, (dict, str))
                ]
                entry["models"] = found
                if provider is None:
                    provider = name
                    models = found
                    api_base = f"{root}/v1" if name == "openai_compatible" else root
            probes.append(entry)
        except Exception as exc:
            probes.append(
                {
                    "provider_candidate": name,
                    "url": url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    return {
        "ok": provider is not None,
        "provider": provider,
        "api_base": api_base,
        "models": models,
        "probes": probes,
    }


# --------------------------------------------------------------------------- #
# generation
# --------------------------------------------------------------------------- #
def _generate(
    provider: str,
    api_base: str,
    model: str,
    prompt: str,
    api_key: Optional[str],
    timeout_s: float,
    max_tokens: int = 64,
) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        if provider == "openai_compatible":
            url = f"{api_base}/chat/completions"
            payload: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": max_tokens,
            }
        else:
            url = f"{api_base}/api/generate"
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_predict": max_tokens},
            }
        response = requests.post(
            url, json=payload, headers=_auth_headers(api_key), timeout=timeout_s
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        response.raise_for_status()
        body = response.json()
        if provider == "openai_compatible":
            message = (body.get("choices") or [{}])[0].get("message") or {}
            text = str(message.get("content") or "")
        else:
            text = str(body.get("response") or "")
        return {"status": "success", "latency_ms": latency_ms, "text": text.strip()}
    except requests.Timeout:
        return {
            "status": "timeout",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except requests.ConnectionError as exc:
        return {"status": "connection_error", "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:
        return {"status": "server_error", "error": f"{type(exc).__name__}: {exc}"}


def _parse_ok_json(text: str) -> Tuple[bool, Optional[str]]:
    """Reuse the repo's tolerant parser when importable; fall back to json.loads."""
    try:
        from core.llm.parsing import parse_json_response  # type: ignore

        parsed = parse_json_response(text, required=("ok",))
        return parsed.status in {"ok", "partial"} and bool(parsed.data.get("ok")), parsed.status
    except Exception:
        try:
            data = json.loads(text)
        except Exception:
            return False, "fallback"
        return bool(isinstance(data, dict) and data.get("ok")), "ok"


# --------------------------------------------------------------------------- #
# check 5 — structured JSON
# --------------------------------------------------------------------------- #
def check_structured_json(
    provider: str,
    api_base: str,
    model: str,
    api_key: Optional[str],
    timeout_s: float,
) -> Dict[str, Any]:
    result = _generate(
        provider, api_base, model, JSON_PROBE_PROMPT, api_key, timeout_s
    )
    if result["status"] != "success":
        return {"ok": False, **result}
    parsed_ok, parse_status = _parse_ok_json(result["text"])
    return {
        "ok": parsed_ok,
        "latency_ms": result["latency_ms"],
        "parse_status": parse_status,
        "response_excerpt": result["text"][:400],
    }


# --------------------------------------------------------------------------- #
# check 6 — parallel smoke
# --------------------------------------------------------------------------- #
def check_parallel(
    provider: str,
    api_base: str,
    model: str,
    api_key: Optional[str],
    timeout_s: float,
    concurrency: int,
) -> Dict[str, Any]:
    prompts = [
        f'Reply with exactly this JSON object and nothing else: {{"ok": true, "n": {i}}}'
        for i in range(concurrency)
    ]
    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(
            pool.map(
                lambda p: _generate(provider, api_base, model, p, api_key, timeout_s),
                prompts,
            )
        )
    wall_s = round(time.perf_counter() - wall_started, 3)

    successes = [r for r in results if r["status"] == "success"]
    latencies = [r["latency_ms"] for r in successes]
    malformed = 0
    for r in successes:
        ok, _ = _parse_ok_json(r["text"])
        if not ok:
            malformed += 1

    statuses: Dict[str, int] = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1

    return {
        "ok": len(successes) == concurrency and malformed == 0,
        "concurrency": concurrency,
        "wall_s": wall_s,
        "status_counts": statuses,
        "success_count": len(successes),
        "malformed_json_count": malformed,
        "latency_ms": {
            "min": round(min(latencies), 1) if latencies else None,
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "max": round(max(latencies), 1) if latencies else None,
        },
    }


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run_preflight(
    base_url: Optional[str],
    host: Optional[str],
    ports: Tuple[int, ...],
    model: Optional[str],
    api_key: Optional[str],
    timeout_s: float,
    concurrency: int,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "phase": "0-B remote GPU / LLM preflight",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "base_url": base_url,
            "host": host,
            "ports": list(ports),
            "model_requested": model,
            "api_key": _redact(api_key),
            "timeout_s": timeout_s,
            "concurrency": concurrency,
        },
        "checks": {},
    }
    checks = report["checks"]

    checks["1_python"] = check_python()

    if base_url:
        resolved_host, resolved_port = _split_base_url(base_url)
        probe_ports = (resolved_port,) if resolved_port else ports
    elif host:
        resolved_host, probe_ports = host, ports
    else:
        checks["2_ping"] = {
            "ok": False,
            "error": f"no endpoint: set {BASE_URL_ENV} or pass --host",
        }
        report["overall_ok"] = False
        report["blocking"] = [
            f"No endpoint configured. Set {BASE_URL_ENV} (or pass --host) after "
            "connecting the VPN."
        ]
        return report

    checks["2_ping"] = check_ping(resolved_host)
    checks["3_tcp"] = check_tcp(resolved_host, tuple(probe_ports))

    open_ports = [p["port"] for p in checks["3_tcp"]["ports"] if p["open"]]
    if not open_ports:
        report["overall_ok"] = False
        report["blocking"] = [
            f"No TCP port open on {resolved_host} ({list(probe_ports)}). "
            "Is the VPN connected and the LLM server running?"
        ]
        return report

    roots = (
        [_root_of(base_url)]
        if base_url
        else [f"http://{resolved_host}:{port}" for port in open_ports]
    )
    health: Dict[str, Any] = {"ok": False}
    for root in roots:
        health = check_health(root, api_key)
        if health["ok"]:
            health["root"] = root
            break
    checks["4_health"] = health

    if not health["ok"]:
        report["overall_ok"] = False
        report["blocking"] = [
            "TCP is open but neither /v1/models nor /api/tags answered 200. "
            "Provider cannot be determined — do not guess an adapter (design rule 13)."
        ]
        return report

    provider = health["provider"]
    api_base = health["api_base"]
    resolved_model = model or (health["models"][0] if health["models"] else None)
    report["config"]["model_resolved"] = resolved_model
    if not resolved_model:
        report["overall_ok"] = False
        report["blocking"] = ["Health API listed no models; set EA_LLM_MODEL explicitly."]
        return report

    checks["5_structured_json"] = check_structured_json(
        provider, api_base, resolved_model, api_key, timeout_s
    )
    checks["6_parallel"] = check_parallel(
        provider, api_base, resolved_model, api_key, timeout_s, concurrency
    )

    report["overall_ok"] = all(
        checks[name]["ok"]
        for name in ("1_python", "3_tcp", "4_health", "5_structured_json", "6_parallel")
    )
    report["gate_0_remote_llm"] = "GO" if report["overall_ok"] else "NO-GO"
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get(BASE_URL_ENV) or None)
    parser.add_argument("--host", default=None, help="private host to scan when no base URL is set")
    parser.add_argument(
        "--ports",
        default=",".join(str(p) for p in DEFAULT_PORTS),
        help="comma-separated candidate ports (default: 8000,8001,11434)",
    )
    parser.add_argument("--model", default=os.environ.get(MODEL_ENV) or None)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="output path (default: src/experiments/results/preflight/preflight_report.json)",
    )
    args = parser.parse_args(argv)

    ports = tuple(int(p) for p in str(args.ports).split(",") if str(p).strip())
    report_path = args.report or (
        Path(__file__).resolve().parents[1]
        / "experiments"
        / "results"
        / "preflight"
        / "preflight_report.json"
    )

    report = run_preflight(
        base_url=args.base_url,
        host=args.host,
        ports=ports,
        model=args.model,
        api_key=os.environ.get(API_KEY_ENV) or None,
        timeout_s=args.timeout_s,
        concurrency=args.concurrency,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nreport written to {report_path}", file=sys.stderr)
    return 0 if report.get("overall_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

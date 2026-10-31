"""Build an offline Japanese report from an actual balancing-cube campaign.

Usage: python -m tools.build_cube_memory_report --run-dir <campaign-directory>

The report embeds compact measured data and uses no external scripts, fonts or
services. Full source artifacts remain linked. It never embeds private model
reasoning; the proposal hypothesis is the only model explanation displayed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, urlunsplit


def _read(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        if isinstance(value, str):
            match = re.match(r"\s*(-?\d+(?:\.\d+)?)", value)
            return float(match.group(1)) if match else None
        return None


def _clean(value):
    """Keep embedded JSON finite, including results from incomplete runs."""
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _safe_url(url):
    try:
        parts = urlsplit(str(url))
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        netloc = f"{host}:{parts.port}" if parts.port is not None else host
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    except ValueError:
        return "invalid endpoint"


def _link(path, output):
    return quote(os.path.relpath(path, output.parent), safe="/.") if path.is_file() else None


def _pick(mapping, keys):
    return {key: mapping[key] for key in keys if key in mapping}


def _memory_projection(memory, root, output):
    projection = _pick(memory, ("schema_version", "retrieval_strategy", "episode_count", "selected_count",
                               "omitted_count", "semantic_memory", "episodic_memory"))
    for episode in projection.get("episodic_memory", []):
        episode["source_links"] = []
        for reference in episode.get("source_refs", []):
            source = reference if isinstance(reference, str) else reference.get("path", "")
            path = Path(source)
            if not path.is_file() and root.name in path.parts:
                position = len(path.parts) - 1 - list(reversed(path.parts)).index(root.name)
                path = root.joinpath(*path.parts[position + 1:])
            elif not path.is_file():
                parts = list(path.parts)
                results_index = next((i for i in range(len(parts) - 2)
                                      if parts[i] == "experiments"
                                      and parts[i + 1] == "balancing_cube"
                                      and parts[i + 2] == "results"), None)
                if results_index is not None:
                    local_candidate = root.parent.joinpath(*parts[results_index + 3:])
                    if local_candidate.is_file():
                        path = local_candidate
            episode["source_links"].append({"path": source, "href": _link(path, output),
                "sha256": reference.get("sha256") if isinstance(reference, dict) else None})
    return projection


def _frames(record):
    frames = record.get("frames") or []
    frames = [frame for frame in frames if isinstance(frame.get("quaternion_wxyz"), list)
              and isinstance(frame.get("position_m"), list)]
    if not frames:
        return []
    step = max(1, math.ceil(len(frames) / 220))
    selected = frames[::step]
    if selected[-1] is not frames[-1]:
        selected.append(frames[-1])
    keys = ("time_s", "position_m", "quaternion_wxyz", "wheel_angle_rad",
            "tilt_total_deg", "pivot_displacement_mm", "wheel_x_rpm", "wheel_y_rpm", "wheel_z_rpm")
    return [_pick(frame, keys) for frame in selected]


def _candidate(result_path, compiled_path, output, *, label=None):
    result, compiled = _read(result_path, {}), _read(compiled_path, {})
    if not result:
        return None
    data = _pick(result, ("candidate_id", "input_digest", "controller_digest", "snapshot_digest",
        "campaign_id", "score", "screening_pass_fraction", "all_screening_passed", "trial_count",
        "numeric_cpu_verified", "numeric_gpu_verified", "gpu_state", "agreement_state", "round",
        "matrix_cell", "stage", "half_step_adjudication_performed"))
    data["candidate_id"] = result.get("candidate_id", compiled.get("id", result_path.parent.name))
    data["label"] = label or data["candidate_id"]
    data["proposal"] = compiled.get("proposal") or result.get("proposal") or {}
    data["mechanics"] = data["proposal"].get("parameters", {})
    data["control"] = data["proposal"].get("control", {})
    data["controller"] = _pick(compiled.get("controller", {}), ("K", "yaw_rate_gain_nm_s", "state_order"))
    data["physics"] = _pick(compiled.get("config", {}).get("physics", {}),
        ("cube_side_m", "timestep_s", "control_period_s", "wheel_radius_m", "wheel_mass_kg", "frame_mass_kg", "wheel_face_inset_m", "wheel_mount_side"))
    data["links"] = {"result": _link(result_path, output), "compiled": _link(compiled_path, output)}
    trials, replays, gpu_workers = [], [], {}
    records = result.get("records", [])
    failure_indices = [i for i, row in enumerate(records)
                       if any(gate.get("passed") is False for gate in row.get("screening", []))]
    replay_indices = list(dict.fromkeys([0, *(failure_indices[:1]), len(records) - 1]))
    for index, row in enumerate(records):
        agreement = row.get("paired_metrics", {})
        trials.append({
            "run_id": row.get("run_id"), "domain": row.get("domain_id"),
            "condition": row.get("condition_id"), "seed": row.get("seed"),
            "summary": _pick(row.get("summary", {}), ("status", "simulated_duration_s", "peak_tilt_deg",
                "final_1s_tilt_rms_deg", "peak_pivot_displacement_mm", "peak_wheel_rpm",
                "contact_fraction", "speed_governor_fraction", "peak_slip_speed_m_s")),
            "gpu_summary": _pick(row.get("gpu_summary", {}), ("status", "simulated_duration_s",
                "peak_tilt_deg", "final_1s_tilt_rms_deg", "peak_pivot_displacement_mm", "peak_wheel_rpm")),
            "screening": row.get("screening", []), "agreement": agreement,
            "gpu_state": row.get("gpu_state", result.get("gpu_state")),
        })
        backend = row.get("gpu_backend", {})
        for worker in backend.get("workers", []):
            gpu_id = str(worker.get("physical_cuda_index", "?"))
            gpu_workers[gpu_id] = _pick(worker, ("physical_cuda_index", "global_case_indices", "batch_size",
                "simulation_wall_time_s", "precision", "backend", "jax_version", "mujoco_version"))
        if index in replay_indices:
            frames = _frames(row)
            if frames:
                replays.append({"case": f"{row.get('domain_id', '')} / {row.get('condition_id', '')} / seed {row.get('seed', '')}",
                    "frames": frames, "case_index": index, "source": "saved native MuJoCo CPU pose frames",
                    "failed": index in failure_indices})
    data["trials"] = trials
    data["replays"] = replays
    data["gpu_workers"] = list(gpu_workers.values())
    return data


def _telemetry(path):
    """Accept common JSONL nvidia-smi samplers; unknown fields stay in source."""
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text().splitlines():
        try:
            sample = json.loads(line)
        except ValueError:
            continue
        if not isinstance(sample, dict):
            continue
        devices = sample.get("gpus", sample.get("devices", sample.get("gpu", [])))
        if isinstance(devices, dict):
            devices = [{"index": key, **value} for key, value in devices.items() if isinstance(value, dict)]
        if not isinstance(devices, list):
            devices = [sample] if "index" in sample else []
        stamp = sample.get("timestamp", sample.get("time", sample.get("checked_at", len(rows))))
        for device in devices:
            if not isinstance(device, dict):
                continue
            def first(*keys):
                return next((device[key] for key in keys if key in device), None)
            rows.append({"time": stamp, "gpu": str(first("index", "id", "gpu_id", "gpu_index")),
                "utilization": _number(first("utilization_gpu", "utilization.gpu", "utilization", "utilization_percent", "gpu_utilization_percent")),
                "memory_mib": _number(first("memory_used_mib", "memory_used_mb", "memory.used", "memory_used", "memory_mib")),
                "power_w": _number(first("power_draw_w", "power.draw", "power_w"))})
    # A bounded chart retains the first and last sample of every device.
    if len(rows) > 5000:
        step = math.ceil(len(rows) / 5000)
        rows = rows[::step] + rows[-8:]
    return rows


def collect(run_dir, output):
    root = Path(run_dir).resolve()
    summary = _read(root / "summary.json", {})
    if not summary and not root.is_dir():
        raise ValueError(f"Run directory does not exist: {root}")
    candidates = [_candidate(path, path.with_name("compiled.json"), output)
                  for path in sorted((root / "candidates").glob("*/result.json"))]
    candidates = [row for row in candidates if row]
    validation = _candidate(root / "validation" / "result.json", root / "validation" / "compiled.json", output,
                            label="独立validation")
    if validation:
        validation["stage"] = "validation"
        candidates.append(validation)
    rounds = []
    logged = {int(row["round"]): row for row in summary.get("rounds", []) if "round" in row}
    for folder in sorted(root.glob("round-*")):
        if not folder.is_dir() or not re.fullmatch(r"round-\d+", folder.name):
            continue
        number = int(folder.name.split("-")[-1])
        prompt = _read(folder / "prompt-data.json", {})
        policy_in = _read(folder / "policy-input.json", {})
        policy_out = _read(folder / "policy-output.json", {})
        proposal = _read(folder / "proposal.json", {})
        memory = prompt.get("agent_memory", {})
        after = _read(folder / "memory-after.json", {})
        log = logged.get(number, {})
        matching = [i for i, item in enumerate(candidates) if item.get("stage") != "validation"
                    and (item.get("round") == number or item["candidate_id"] in log.get("candidate_ids", []))]
        artifacts = ["prompt-data.json", "ssot-context.json", "proposal.json", "policy-input.json",
                     "policy-output.json", "memory-after.json", "rejected.json", "failed.json", "pending.json"]
        links = {name: _link(folder / name, output) for name in artifacts if (folder / name).is_file()}
        retries = []
        for rejected in sorted(folder.glob("attempt-*-rejected.json")):
            rejected_data = _read(rejected, {})
            retries.append({"attempt": rejected.name, "error": rejected_data.get("error"), "link": _link(rejected, output)})
        rounds.append({"number": number, "log": log, "policy_in": policy_in, "policy_out": policy_out,
            "proposal": proposal, "prompt_chars": len(json.dumps(prompt, ensure_ascii=False, separators=(",", ":"))),
            "memory": _memory_projection(memory, root, output),
            "memory_after": _memory_projection(after, root, output),
            "candidate_indices": matching, "links": links, "retries": retries, "traces": [],
            "current_best": _pick(prompt.get("current_best") or {}, ("proposal", "feedback")),
            "source_context_digest": prompt.get("source_context_digest"),
        })
    traces = []
    for path in sorted((root / "llm-trace").glob("*.json")):
        raw = _read(path, {})
        if not raw:
            continue
        request = _pick(raw.get("request", {}), ("model", "prompt_sha256", "prompt_char_count", "prompt_byte_count",
            "prompt_file", "temperature", "requested_max_tokens", "max_tokens", "repetition_penalty", "think",
            "thinking_token_budget", "api_timeout_seconds", "prompt_token_count", "context_window", "prompt_fit_method"))
        request["url"] = _safe_url(raw.get("request", {}).get("url", ""))
        trace = _pick(raw, ("request_id", "started_at", "status", "http_status", "wall_seconds", "error_type"))
        trace["request"] = request
        trace["response"] = _pick(raw.get("response", {}), ("id", "model", "usage", "finish_reason", "reasoning_char_count"))
        trace["link"] = _link(path, output)
        exact_prompt = _read(path.parent / request.get("prompt_file", "missing"), {})
        policy_revision = exact_prompt.get("policy", {}).get("revision") if isinstance(exact_prompt, dict) else None
        trace["round"] = next((row["number"] for row in rounds if policy_revision is not None
                               and row["policy_in"].get("revision") == policy_revision), None)
        traces.append(trace)
    traces.sort(key=lambda row: str(row.get("started_at", "")))
    for trace in traces:
        if trace["round"] is not None:
            next(row for row in rounds if row["number"] == trace["round"])["traces"].append(trace)
    snapshot = _read(root / "frozen-snapshot.json", {})
    first_context = _read(root / "round-01" / "ssot-context.json", {})
    kinds = Counter(row.get("kind", "unknown") for row in first_context.get("records", []))
    comparison_ref = snapshot.get("comparison_design_ref", {})
    comparison = next((row for row in first_context.get("records", [])
                       if row.get("id") == comparison_ref.get("id")
                       and row.get("revision") == comparison_ref.get("revision")), {})
    reference_settings = _pick(comparison.get("data", {}), ("family", "parameters"))
    if snapshot.get("controller"):
        reference_settings["control"] = {"tilt_q_scale": 1.0, "rate_q_scale": 1.0,
            "momentum_q_scale": 1.0, "yaw_rate_gain_nm_s": snapshot["controller"].get("yaw_rate_gain_nm_s")}
    sources = []
    for name in ("summary.json", "execution-manifest.json", "frozen-snapshot.json", "environment.json",
                 "sync-status.json", "onepiece-outbox.json", "gpu-telemetry.jsonl", "policy-initial.json"):
        path = root / name
        if path.is_file():
            sources.append({"name": name, "href": _link(path, output), "bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return _clean({"summary": summary, "candidates": candidates, "rounds": rounds, "traces": traces,
        "telemetry": _telemetry(root / "gpu-telemetry.jsonl"),
        "manifest": _read(root / "execution-manifest.json", {}), "sources": sources,
        "context_counts": dict(kinds), "contract": snapshot.get("contract", {}),
        "reference_settings": reference_settings, "comparison_design_ref": comparison_ref,
        "objective": snapshot.get("plan", {}).get("objective", {}),
        "generated_at": datetime.now().astimezone().isoformat(), "run_directory": str(root)})


_HTML = r'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>実測の設計反復 | One-Piece × Qwen × MuJoCo</title><style>
:root{--ink:#193040;--muted:#5d7180;--paper:#f3f1ea;--white:#fffefa;--line:#cfd9d9;--blue:#236b8d;--teal:#247f6c;--orange:#cb7937;--red:#a5463f;--pale:#e5eef0}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif}a{color:var(--blue);text-underline-offset:3px}button,select,input{font:inherit}button,select{border:1px solid var(--line);border-radius:6px;background:white;color:var(--ink);padding:7px 11px}button{cursor:pointer}button:hover{background:var(--pale)}h1,h2,h3,p{margin-top:0}h2{font-size:25px;line-height:1.35;margin-bottom:10px}h3{font-size:17px;margin-bottom:8px}header{padding:45px max(22px,calc((100vw - 1220px)/2));background:#183e52;color:#fff;position:relative;overflow:hidden}header:after{content:"";position:absolute;right:-90px;top:-160px;width:440px;height:440px;border:1px solid #ffffff24;border-radius:50%;box-shadow:0 0 0 45px #ffffff09,0 0 0 90px #ffffff05}header>*{position:relative;z-index:1}.eyebrow{font-size:11px;letter-spacing:.15em;color:#b5dce0}h1{font-size:clamp(29px,4vw,48px);line-height:1.2;margin:14px 0}header p{max-width:910px;color:#d8e7e9;margin-bottom:10px}.mono,code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.mono{font-size:11px;overflow-wrap:anywhere}.runid{color:#b4d0d5;font-size:11px}.wrap{max-width:1264px;margin:auto;padding:26px 22px}.topline{display:grid;grid-template-columns:1.3fr 1fr;gap:30px;padding:8px 0 22px;border-bottom:1px solid var(--line)}.conclusion{font-size:20px;line-height:1.5}.sub{font-size:12px;color:var(--muted)}.scope{border-left:3px solid var(--orange);padding:3px 0 3px 15px;font-size:12px;color:var(--muted)}.scope b{color:var(--ink)}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:20px;margin:25px 0 33px}.metric{border-bottom:3px solid var(--line);padding-bottom:11px}.metric strong{display:block;font-size:28px;line-height:1.3;font-variant-numeric:tabular-nums}.metric span{font-size:11px;color:var(--muted)}section{margin:38px 0}.sectionhead{display:flex;justify-content:space-between;align-items:end;gap:20px}.sectionhead p{font-size:12px;color:var(--muted);max-width:610px}.paper{border:1px solid var(--line);background:var(--white);padding:22px;border-radius:10px}.flow{display:grid;grid-template-columns:repeat(6,1fr);gap:18px;margin-top:19px}.flow>div{position:relative;border-top:4px solid var(--blue);padding:13px 6px 8px;background:#f9faf6}.flow>div:nth-child(3){border-color:var(--orange)}.flow>div:nth-child(5),.flow>div:nth-child(6){border-color:var(--teal)}.flow>div:not(:last-child):after{content:"→";position:absolute;right:-17px;top:29px;color:#8c9fa4}.flow small{font:10px ui-monospace,monospace;color:var(--muted)}.flow b{display:block;font-size:13px;margin:7px 0}.flow span{display:block;font-size:11px;color:var(--muted)}.return{margin-top:14px;background:#e6efe9;border-left:3px solid var(--teal);padding:10px 14px;font-size:12px}.chartbox{background:var(--white);border:1px solid var(--line);padding:16px;border-radius:9px}canvas{width:100%;display:block}.chartbox canvas{height:265px}.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:11px;color:var(--muted);margin-top:8px}.legend i{display:inline-block;width:18px;height:3px;vertical-align:middle;margin-right:5px}.roundnav{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:14px 0}.roundnav button.active{background:var(--ink);color:white;border-color:var(--ink)}.roundnav button.good{border-bottom:3px solid var(--teal)}.roundnav button.bad{border-bottom:3px solid var(--orange)}.roundlayout{display:grid;grid-template-columns:1.15fr .85fr;gap:27px}.hypothesis{border-left:4px solid var(--orange);padding:15px 17px;background:#f7eada;font-size:14px;overflow-wrap:anywhere}.tag{display:inline-block;padding:3px 8px;border-radius:99px;background:#e7edef;font-size:10px;white-space:nowrap}.tag.pass{background:#dfefe8;color:#246a54}.tag.fail{background:#f5e3de;color:#9c453d}.tag.pending{background:#f2ead2;color:#806822}.roundtitle{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.roundtitle h3{margin:0}.rowscroll{max-height:340px;overflow:auto}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:11px}th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}thead th{color:var(--muted);font-size:10px;background:#eaf0f0;position:sticky;top:0}td.num{text-align:right;font-variant-numeric:tabular-nums}.changed{background:#faebd9}.roundlinks,.sourcelinks{display:flex;gap:8px;flex-wrap:wrap;margin:13px 0}.roundlinks a,.sourcelinks a{font-size:11px;padding:5px 8px;border:1px solid var(--line);background:white;border-radius:5px}.memoryfact{display:flex;gap:24px;margin:14px 0}.memoryfact strong{font-size:26px;display:block}.memoryfact span{font-size:11px;color:var(--muted)}.notice{border-left:3px solid var(--blue);background:#e6eef0;padding:11px 14px;font-size:12px;margin:13px 0}.empty{color:var(--muted);font-size:12px;padding:20px 0}.split{display:grid;grid-template-columns:1fr 1fr;gap:25px}.endpoint{font-size:12px;overflow-wrap:anywhere;margin:12px 0;background:#edf1ee;padding:12px}.kv{display:grid;grid-template-columns:145px 1fr;gap:0;font-size:12px}.kv>div{padding:6px 0;border-bottom:1px solid #e0e6e3;overflow-wrap:anywhere}.kv>div:nth-child(odd){color:var(--muted)}details{margin:12px 0;border:1px solid var(--line);border-radius:6px;background:white}summary{cursor:pointer;padding:10px 12px;font-size:12px;font-weight:600}details pre{margin:0;padding:10px 14px;overflow:auto;font-size:11px;max-height:360px}.failurelist{margin:0;padding:0;list-style:none}.failurelist li{padding:8px 0;border-bottom:1px solid var(--line);font-size:11px}.candidatebar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:15px 0}.candidatebar select{max-width:100%;font-size:12px}.replay{background:#102b3c;color:#d7e5e8;border-radius:9px;overflow:hidden}.replay canvas{height:315px}.replaytools{display:flex;align-items:center;gap:10px;padding:10px 14px;font-size:11px;flex-wrap:wrap}.replaytools input{flex:1;min-width:100px}.replaytools select{max-width:85%;font-size:11px}.replaytools button{font-size:11px}.caption{font-size:10px;color:var(--muted);margin-top:7px}.assignment{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}.assignment>div{border-top:3px solid var(--blue);background:#e9f0ed;padding:9px;min-width:94px;font-size:11px}.assignment b{display:block}.manifest{white-space:pre-wrap;overflow-wrap:anywhere}footer{border-top:1px solid var(--line);padding:20px 0 25px;font-size:10px;color:var(--muted)}.errorline{color:var(--red)}
@media(max-width:1000px){.flow{grid-template-columns:repeat(3,1fr)}.flow>div:nth-child(3):after{display:none}.metrics{grid-template-columns:repeat(3,1fr)}.roundlayout{grid-template-columns:1fr}.split{grid-template-columns:1fr}.roundlayout>.paper{padding:15px}}@media(max-width:620px){.wrap{padding:20px 13px}header{padding:30px 17px}.topline{grid-template-columns:1fr;gap:15px}.metrics{grid-template-columns:repeat(2,1fr);gap:15px}.flow{grid-template-columns:repeat(2,1fr);gap:10px}.flow>div:after{display:none}.sectionhead{display:block}.paper{padding:14px}.kv{grid-template-columns:115px 1fr}h2{font-size:22px}.replay canvas{height:250px}}
</style></head><body>
<header><div class="eyebrow">ENGINEERING AGENTS / EVIDENCE-BACKED DESIGN MEMORY</div><h1>記録を読み、設計し、試験する。<br>測定結果から次の設計へ。</h1><p id="heroText"></p><div class="runid mono" id="runid"></div></header>
<main class="wrap"><div class="topline"><div><div class="conclusion" id="conclusion"></div><div class="sub" id="stop"></div></div><div class="scope"><b>6秒の数値開発試験と、実機の30秒保持を区別します。</b><br>CPUの数値ゲート通過、CPU/GPUの整合、独立validationを別々に表示します。実機・物理忠実度・電力・温度の妥当性は未確認です。設計の正式採用と要求変更は人間が決めます。</div></div><div class="metrics" id="metrics"></div>
<section><div class="sectionhead"><h2>今回動いたパイプライン</h2><p>順序のある反復です。各回の試験完了と記録を待ち、結果を次の提案入力に渡します。下の表示は保存済み成果物から生成しました。</p></div><div class="paper"><div class="flow"><div><small>1 / SSOT</small><b>One-Pieceを読む</b><span id="contextCount"></span></div><div><small>2 / MEMORY</small><b>関連する経験を検索</b><span>最高スコア・直近・異なる失敗・同じ構成の過去試験を選ぶ。</span></div><div><small>3 / PROPOSAL</small><b id="modelFlow">LLMが変更を提案</b><span>許可された機械・制御の設定と仮説をJSONで返す。</span></div><div><small>4 / SIMULATION</small><b>CPUとMJX GPUで試験</b><span>compilerが構成とKを固定。同じ条件を別経路で計算する。</span></div><div><small>5 / VERIFICATION</small><b>数値ゲートと整合を判定</b><span>LLMから独立した判定器が、固定の要求・条件と比較する。</span></div><div><small>6 / WRITE BACK</small><b>証拠・経験・方針を保存</b><span>One-Pieceと経験ログに保存し、次回の入力として再取得する。</span></div></div><div class="return">↶ 次回へ：測定した失敗と改善 → 検索する記憶 → 新しい仮説 → 次の実試験</div></div></section>
<section><div class="sectionhead"><h2>反復の推移</h2><p>青は各回の提案結果、緑は探索中の最高スコア。通過率はケース単位で全ゲートを通った割合です。CPU評価が成立していても全ケース合格とは限りません。</p></div><div class="chartbox"><canvas id="scoreChart" aria-label="反復ごとの数値スコアとケース通過率"></canvas><div class="legend"><span><i style="background:#236b8d"></i>提案スコア</span><span><i style="background:#247f6c"></i>探索中の最高</span><span><i style="background:#cb7937"></i>ケース通過率</span><span>横軸：反復番号 / 縦軸：数値スコアまたは割合</span></div></div><div class="notice" id="roundCaution"></div><div class="roundnav" id="roundnav"></div><div class="roundlayout"><article><div class="roundtitle"><h3 id="roundTitle"></h3><span id="roundStatus"></span></div><p class="sub" id="roundFeedback"></p><div class="hypothesis"><small class="sub">LLMが最終回答に書いた仮説 / 測定事実とは区別</small><div id="hypothesis"></div></div><div class="roundlinks" id="roundLinks"></div><h3>比較元からの設計差分</h3><p class="sub">機械は6変数と登録モータ、制御はQの3群とyawゲインに限定。空欄は記録に値がない項目です。</p><div class="tablewrap"><table><thead><tr><th>設定 / 単位</th><th>比較元</th><th>今回の提案</th><th>差</th></tr></thead><tbody id="deltaRows"></tbody></table></div><div id="retryList"></div></article><aside class="paper"><h3>今回の提案で読んだ記憶</h3><p class="sub" id="memoryStrategy"></p><div class="memoryfact" id="memoryCounts"></div><div class="rowscroll"><table><thead><tr><th>経験</th><th>測定結果 / 選択理由</th></tr></thead><tbody id="memoryRows"></tbody></table></div><div class="notice" id="memoryAfter"></div><h3>方針の更新</h3><p class="sub" id="policyChange"></p><div id="semanticFailures"></div></aside></div></section>
<section><div class="sectionhead"><h2>CPU・GPUの検証とシミュレーション</h2><p>ケース単位の合否、CPU/GPU整合の測定値と失敗原因を調べられます。独立validationは探索に使ったケースと分けて表示します。</p></div><div class="candidatebar"><label for="candidateSelect">確認する構成</label><select id="candidateSelect"></select><span id="candidateStatus"></span></div><div class="split"><div><div class="kv" id="candidateFacts"></div><div class="assignment" id="gpuAssignment"></div><h3 style="margin-top:18px">不成立の条件</h3><ul class="failurelist" id="failureList"></ul><div class="roundlinks" id="candidateLinks"></div></div><div><div class="replay"><canvas id="replayCanvas" aria-label="保存済みCPU姿勢からの3D再生"></canvas><div class="replaytools"><select id="replaySelect"></select><button id="playButton">再生</button><input id="replaySlider" type="range" min="0" max="1" value="0"><span id="replayTime"></span></div></div><div class="caption" id="replayCaption"></div></div></div><div class="tablewrap" style="margin-top:20px"><table><thead><tr><th>ケース</th><th>CPUゲート</th><th>CPU/GPU整合</th><th>CPU → GPU / tilt RMS deg</th><th>整合RMSE tilt deg / ω deg/s / pivot mm</th><th>時間 s</th><th>失敗・未確認</th></tr></thead><tbody id="trialRows"></tbody></table></div></section>
<section><div class="sectionhead"><h2>どのLLMを、どう実行したか</h2><p>クライアントの要求とサーバーが返したモデル名を区別します。推論の非公開思考本文は表示・埋込みせず、最終提案の仮説だけを示します。</p></div><div class="split"><div class="paper"><h3>接続先と生成条件</h3><div class="endpoint mono" id="endpoint"></div><div class="kv" id="llmOptions"></div><p class="sub">Qwenの重みを学習し直す処理ではありません。数値フィードバックで探索方針と検索する経験を変え、同じ推論サーバーへ次の提案を依頼します。</p></div><div><h3>エージェントの記憶設計</h3><p class="sub">Agent Memory Techniquesのepisodic・semantic・working・self-reflection・retrieval・cross-sessionの考え方を、小さい設計データ向けに実装しています。測定値と未検証の仮説を区別します。</p><div class="kv"><div>経験記憶</div><div>構成digest、提案、測定フィードバック、原成果物参照を追記。</div><div>意味記憶</div><div>失敗項目の出現数など、測定された事実を集計。相関は因果を示しません。</div><div>作業記憶</div><div>固定要求・現在の最良設計・検索した経験を各回のpromptへ。</div><div>検索</div><div>構成一致、最高スコア、直近、キーワードに近い異なる失敗を優先。</div><div>継続性・完全性</div><div>版とハッシュを記録。過去runを出典付きで読込み、重複設定を区別。</div></div><p class="sub"><a href="https://github.com/NirDiamant/Agent_Memory_Techniques" target="_blank" rel="noreferrer">参考：Agent Memory Techniques</a></p></div></div><div class="tablewrap" style="margin-top:18px"><table><thead><tr><th>回 / 要求</th><th>モデル / 終了理由</th><th>prompt文字数</th><th>token入力 / 出力</th><th>経過 s</th><th>HTTP / 状態</th><th>記録</th></tr></thead><tbody id="traceRows"></tbody></table></div><div class="notice" id="traceLimit"></div><details><summary>実行manifest（保存されている場合）</summary><pre id="manifest"></pre></details></section>
<section><div class="sectionhead"><h2>GPUサーバーの使用実績</h2><p>割当てと実測使用率は別の情報です。GPUを指定しただけで使用率最大や高速化達成とは判定しません。</p></div><div class="assignment" id="serverAssignment"></div><div class="chartbox"><canvas id="gpuChart" aria-label="GPUごとの使用率推移"></canvas><div class="legend" id="gpuLegend"></div></div><div class="sub" id="telemetrySummary" style="margin:10px 0"></div><div class="tablewrap"><table><thead><tr><th>GPU</th><th>観測点</th><th>使用率 平均 / 最大 %</th><th>メモリ 最大 MiB</th><th>電力 最大 W</th></tr></thead><tbody id="telemetryRows"></tbody></table></div></section>
<section><div class="sectionhead"><h2>元データと判定の境界</h2><p>可視化の要約と原本を行き来できます。表と図は同じJSONから作成しています。</p></div><div class="split"><div><h3>凍結した数値ゲート</h3><div class="tablewrap"><table><thead><tr><th>測定項目</th><th>条件</th><th>単位</th></tr></thead><tbody id="gateRows"></tbody></table></div></div><div><h3>出典</h3><div class="sourcelinks" id="sources"></div><p class="sub" id="ssotFacts"></p><details><summary>出典ファイルのSHA-256</summary><pre id="sourceHashes"></pre></details><p class="scope">記録したもの：数値探索、固定dtでのCPU/GPU確認、候補比較、エージェントの経験。<br>未実施：実機30秒保持、物理妥当性、人間による正式baseline確定。半刻み確認は今回のパイプラインに含めません。</p></div></div></section><footer id="footer"></footer></main>
<script id="report-data" type="application/json">__DATA__</script><script>
"use strict";
const D=JSON.parse(document.getElementById('report-data').textContent), S=D.summary||{}, C=D.candidates||[], R=D.rounds||[];
const $=id=>document.getElementById(id), esc=v=>String(v??'—').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const num=(v,n=4)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(n):'—';
const pct=v=>typeof v==='number'?num(v*100,1)+'%':'—';
const flag=(v,yes='成立',no='未確認')=>`<span class="tag ${v===true?'pass':v===false?'pending':''}">${v===true?yes:no}</span>`;
const link=(href,label)=>href?`<a href="${esc(href)}" download>${esc(label)}</a>`:'';
const kv=(key,value)=>`<div>${esc(key)}</div><div>${value}</div>`;
const allTraces=D.traces||[], models=[...new Set(allTraces.map(t=>t.request?.model).filter(Boolean))], served=[...new Set(allTraces.map(t=>t.response?.model).filter(Boolean))];
const best=S.best||{}, validation=S.validation||{}, ref=C.find(c=>c.candidate_id==='reference'&&c.stage!=='validation')||C[0];
const improved=ref&&typeof best.score==='number'&&best.score>ref.score+1e-12;
const validationCandidate=C.find(c=>c.stage==='validation');
const validationFailures=[...new Set((validationCandidate?.trials||[]).flatMap(t=>(t.screening||[]).filter(g=>g.passed===false).map(g=>`${g.metric} ${num(g.value)} ${g.operator||''} ${g.limit??''}`)))];
$('heroText').textContent=`${S.iterations_completed??R.filter(r=>r.log.feedback).length}回の完了した設計反復を、提案・数値試験・記憶・再提案の順で追います。${models.length?models.join(' / '):'モデルの実行traceはこのrunにありません。'}`;
$('runid').textContent=`RUN ${S.run_id||'記録未完了'} / ${S.status||'summary未取得'} / generated ${D.generated_at}`;
$('conclusion').textContent=best.candidate_id?(improved?`探索スコア ${num(best.score)} は基準 ${num(ref?.score)} から改善。暫定最良構成：${best.candidate_id}。独立validationは${num((validation.screening_pass_fraction||0)*(validation.trial_count||0),0)}/${validation.trial_count??'—'}ケースが全ゲート通過${validationFailures.length?`。不通過: ${validationFailures.slice(0,3).join(' / ')}`:''}。選択状態: ${S.selection_status||'未記録'}。`:`探索の最良構成：${best.candidate_id}。比較基準からのスコア改善は記録されていません。独立validation ${pct(validation.screening_pass_fraction)}。`):'最良構成は未確定です。保存済みの途中結果を表示しています。';
$('roundCaution').textContent=`完了した試験反復 ${S.iterations_completed??0}回 / 保存した提案回 ${S.proposal_rounds_recorded??R.length}回。棄却された提案、未完了試験、重複による再利用は、完了した新規試験と区別します。独立validationは評価した探索構成数に加算しません。`;
$('stop').textContent=`停止理由 ${S.stopped_reason||'未記録'} / 選択状態 ${S.selection_status||'未記録'} / 全体 ${num(S.wall_time_s,1)} 秒`;
const gpuIds=[...new Set(C.flatMap(c=>(c.gpu_workers||[]).map(w=>String(w.physical_cuda_index))))];
$('metrics').innerHTML=[['完了した反復',`${S.iterations_completed??0} / ${S.iterations_requested??'—'}`,'要求した回数との比較'],['評価した構成',String(S.candidates_evaluated??C.filter(c=>c.stage!=='validation').length),'比較基準・2×2の補助構成を含む'],['探索の最高スコア',num(best.score),'固定された数値目的関数'],['独立validation',pct(validation.screening_pass_fraction),`CPU/GPU整合 ${validation.numeric_gpu_verified===true?'成立':'未確認'}`],['LLM要求 / 使用GPU',`${allTraces.length} / ${gpuIds.length}`,`記録のある要求数 / MJX実行GPU数`]].map(m=>`<div class="metric"><span>${esc(m[0])}</span><strong>${esc(m[1])}</strong><span>${esc(m[2])}</span></div>`).join('');
$('contextCount').textContent=`要求 ${D.context_counts.requirement??'—'}件 / KDP ${D.context_counts.kdp??'—'}件。固定した版と過去の設計・試験証拠を取得。`;
if(models.length)$('modelFlow').textContent=`${models.join(' / ')}が提案`;

function chart(canvas,series,{min=0,max=1,xlabels=[],selected=null,empty='測定データはありません。'}={}){
 const box=canvas.getBoundingClientRect(),w=Math.max(280,box.width),h=box.height||260,dpr=window.devicePixelRatio||1; canvas.width=w*dpr;canvas.height=h*dpr;
 const x=canvas.getContext('2d');x.scale(dpr,dpr);x.clearRect(0,0,w,h);const left=43,right=18,top=18,bottom=32,cw=w-left-right,ch=h-top-bottom;
 if(!series.some(s=>s.values.some(v=>typeof v==='number'))){x.fillStyle='#5d7180';x.font='12px system-ui';x.fillText(empty,20,h/2);return;}
 if(min===max)max=min+1; x.font='10px system-ui';x.textAlign='right';x.fillStyle='#5d7180';
 for(let k=0;k<=4;k++){const y=top+k*ch/4;x.strokeStyle='#d8e0df';x.beginPath();x.moveTo(left,y);x.lineTo(w-right,y);x.stroke();x.fillText((max-k*(max-min)/4).toFixed(2),left-8,y+4);}
 const count=Math.max(...series.map(s=>s.values.length)),px=i=>left+(count<=1?cw/2:i*cw/(count-1)),py=v=>top+(max-v)*ch/(max-min);
 if(selected!==null&&count>1){x.fillStyle='#cb793715';x.fillRect(px(selected)-8,top,16,ch);}
 series.forEach(s=>{x.strokeStyle=s.color;x.lineWidth=s.width||2;x.setLineDash(s.dash||[]);x.beginPath();let open=false;s.values.forEach((v,i)=>{if(typeof v!=='number'){open=false;return;}open?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v));open=true;});x.stroke();x.setLineDash([]);if(count<35)s.values.forEach((v,i)=>{if(typeof v==='number'){x.fillStyle=s.color;x.beginPath();x.arc(px(i),py(v),3.2,0,Math.PI*2);x.fill();}});});
 x.textAlign='center';x.fillStyle='#5d7180';for(let i=0;i<count;i++){if(count>20&&i%Math.ceil(count/9)!==0&&i!==count-1)continue;x.fillText(xlabels[i]??i,px(i),h-10);}
}
let roundIndex=0,candidateIndex=0,replayIndex=0,frameIndex=0,playing=false,lastAnimation=0;
function drawScores(){let current=ref?.score??null;const bests=R.map(r=>{const vals=r.candidate_indices.map(i=>C[i]?.score).filter(v=>typeof v==='number');vals.forEach(v=>current=current===null?v:Math.max(current,v));return current;});const scores=R.map(r=>r.log.feedback?.score??null),passes=R.map(r=>{const c=C[r.candidate_indices.at(-1)];return c?.screening_pass_fraction??null;}),values=[0,1,...scores,...bests].filter(v=>typeof v==='number');chart($('scoreChart'),[{values:scores,color:'#236b8d'},{values:bests,color:'#247f6c',width:3},{values:passes,color:'#cb7937',dash:[5,4]}],{min:Math.min(...values),max:Math.max(...values),xlabels:R.map(r=>r.number),selected:roundIndex});}
const fields=[['family','モータ / 登録ID'],['side_m','side_m / m'],['print_mass_ref_kg','print_mass_ref_kg / kg'],['wheel_mass_kg','wheel_mass_kg / kg'],['wheel_radius_ratio','wheel_radius_ratio / 1'],['inner_radius_ratio','inner_radius_ratio / 1'],['wheel_thickness_m','wheel_thickness_m / m'],['tilt_q_scale','姿勢Q倍率 / 1'],['rate_q_scale','角速度Q倍率 / 1'],['momentum_q_scale','運動量Q倍率 / 1'],['yaw_rate_gain_nm_s','yawゲイン / N m s/rad']];
function settings(p){const base=D.reference_settings||{},selected=p.family==='reference'?base:p;return {family:selected.family,...(selected.parameters||{}),...(base.control||{}),...(selected.control||{})};}
function memoryHTML(memory){return (memory.episodic_memory||[]).map(e=>{const f=e.measured_feedback||{};return `<tr><td><b>round ${esc(e.round)}</b><br><span class="mono">${esc((e.run_id||'').slice(-22))}</span><br>${esc(e.status)}</td><td>score ${num(f.score)} / GPU整合 ${f.numeric_gpu_verified===true?'成立':'未確認'}<br>${esc((e.selection_reasons||[]).join(' · '))}<br><span class="mono">${esc((e.configuration_digest||'').slice(0,20))}</span><br>${esc((f.failure_metrics||[]).join(', '))}<details><summary>経験IDと出典 ${(e.source_links||[]).length}件</summary><div class="mono" style="padding:8px">${esc(e.episode_id)}${(e.source_links||[]).map(s=>'<p>'+link(s.href,'元データ')+' '+esc(s.path)+'<br>'+esc(s.sha256||'')+'</p>').join('')}</div></details></td></tr>`;}).join('')||'<tr><td colspan="2">このrunでは記憶検索の記録がありません。</td></tr>';}
function selectRound(index){roundIndex=index;const r=R[index];if(!r)return;document.querySelectorAll('#roundnav button').forEach((b,i)=>b.classList.toggle('active',i===index));$('roundTitle').textContent=`反復 ${r.number} / 方針 ${r.policy_in.revision??'—'} → ${r.policy_out.revision??'—'}`;$('roundStatus').innerHTML=flag(r.log.improved===true,'探索最高を更新','最高の更新なし');const f=r.log.feedback||{};$('roundFeedback').textContent=`候補 ${f.candidate_id||r.proposal.id||'未記録'} / score ${num(f.score)} / ${r.log.context_reread===true?'One-Pieceを再取得':'再取得の記録なし'} / cells ${(r.log.factorial_cells||[]).join(', ')||'—'}`;$('hypothesis').textContent=r.proposal.hypothesis||'最終提案の仮説は記録されていません。';$('roundLinks').innerHTML=Object.entries(r.links).map(([n,h])=>link(h,n)).join('');let previous=r.current_best.proposal||ref?.proposal||{};const next=settings(r.proposal),before=settings(previous);$('deltaRows').innerHTML=fields.map(([key,label])=>{const a=before[key],b=next[key],different=a!==undefined&&b!==undefined&&a!==b;return `<tr class="${different?'changed':''}"><td>${esc(label)}</td><td>${typeof a==='number'?num(a,7):esc(a)}</td><td>${typeof b==='number'?num(b,7):esc(b)}</td><td>${different?(typeof a==='number'&&typeof b==='number'?num(b-a,7):'変更'):'—'}</td></tr>`;}).join('');const m=r.memory||{};$('memoryStrategy').textContent=m.retrieval_strategy||'このrunには永続エージェント記憶の記録がありません。';$('memoryCounts').innerHTML=[['蓄積',m.episode_count],['検索',m.selected_count],['入力から省略',m.omitted_count]].map(([a,b])=>`<div><strong>${esc(b)}</strong><span>${a}</span></div>`).join('');$('memoryRows').innerHTML=memoryHTML(m);$('memoryAfter').textContent=r.memory_after.episode_count!==undefined?`試験後の記憶：${r.memory_after.episode_count}経験。次回promptで再検索します。`:'試験後の記憶投影はこのrunにありません。';$('policyChange').textContent=r.policy_out.hypothesis||'方針更新の記録がありません。';const freq=(r.memory_after.semantic_memory||m.semantic_memory||{}).failure_metric_episode_counts||{};$('semanticFailures').innerHTML=Object.entries(freq).slice(0,7).map(([k,v])=>`<div class="sub">${esc(k)} <b>${esc(v)}経験</b></div>`).join('');$('retryList').innerHTML=r.retries.length?`<h3 style="margin-top:15px">提案の修正試行 ${r.retries.length}件</h3>`+r.retries.map(t=>`<p class="sub errorline">${esc(t.attempt)}: ${esc(t.error)} ${link(t.link,'元記録')}</p>`).join(''):'';if(r.candidate_indices.length)selectCandidate(r.candidate_indices.at(-1));drawScores();}
$('roundnav').innerHTML=R.map((r,i)=>`<button data-round="${i}" class="${r.log.improved?'good':'bad'}">${r.number}</button>`).join('')||'<span class="empty">反復成果物はまだありません。</span>';
$('roundnav').addEventListener('click',e=>{const b=e.target.closest('button');if(b)selectRound(Number(b.dataset.round));});
$('candidateSelect').innerHTML=C.map((c,i)=>`<option value="${i}">${esc(c.stage==='validation'?'VALIDATION':c.round===0?'REFERENCE':'R'+(c.round??'?'))} / ${esc(c.matrix_cell||'')} / ${esc(c.candidate_id)}</option>`).join('');$('candidateSelect').addEventListener('change',e=>selectCandidate(Number(e.target.value)));
function agreementFailures(t){const a=t.agreement||{},v=a.values||{},contract=D.contract.cpu_gpu_agreement||{},messages=[];for(const rule of contract.pre_divergence_tolerances||[]){let limit=rule.limit;if(limit===undefined&&rule.metric==='wheel_peak_difference_rpm'){const match=(rule.rule||'').match(/max\((\d+(?:\.\d+)?) rpm, (\d+(?:\.\d+)?) \* abs/);if(match)limit=Math.max(Number(match[1]),Number(match[2])*Math.abs(t.summary.peak_wheel_rpm||0));}if(typeof v[rule.metric]==='number'&&typeof limit==='number'&&v[rule.metric]>limit)messages.push(`${rule.metric}: ${num(v[rule.metric])} > ${num(limit)}`);}if(t.gpu_summary.status&&t.summary.status!==t.gpu_summary.status)messages.push(`終了状態不一致: ${t.summary.status} / ${t.gpu_summary.status}`);if(typeof t.gpu_summary.simulated_duration_s==='number'&&Math.abs(t.summary.simulated_duration_s-t.gpu_summary.simulated_duration_s)>(contract.termination_time_tolerance_s??Infinity))messages.push('CPU/GPU終了時刻の許容差超過');return messages;}
function selectCandidate(index){candidateIndex=index;const c=C[index];if(!c)return;$('candidateSelect').value=String(index);$('candidateStatus').innerHTML=flag(c.all_screening_passed,'全ケース通過','失敗ケースあり')+' '+flag(c.numeric_gpu_verified,'CPU/GPU整合成立','CPU/GPU整合未確認');const passCount=c.trials.filter(t=>t.screening.length&&t.screening.every(g=>g.passed===true)).length;$('candidateFacts').innerHTML=kv('数値スコア',num(c.score))+kv('ケース通過',`${passCount} / ${c.trial_count??c.trials.length} (${pct(c.screening_pass_fraction)})`)+kv('CPU評価成立',flag(c.numeric_cpu_verified))+kv('GPU実行',esc(c.gpu_state))+kv('CPU/GPU整合',esc(c.agreement_state))+kv('物理刻み / 制御周期',`${num(c.physics.timestep_s,4)} s / ${num(c.physics.control_period_s,4)} s`)+kv('固定K digest',`<span class="mono">${esc(c.controller_digest)}</span>`)+kv('構成digest',`<span class="mono">${esc(c.input_digest)}</span>`);$('gpuAssignment').innerHTML=c.gpu_workers.map(w=>`<div><b>GPU ${esc(w.physical_cuda_index)}</b>case ${(w.global_case_indices||[]).map(i=>i+1).join(', ')}<br>${esc(w.precision||'')}</div>`).join('')||'<span class="sub">GPUごとの実行割当ては記録されていません。</span>';const fails={};c.trials.forEach(t=>{t.screening.filter(g=>g.passed===false).forEach(g=>{fails[g.metric]=(fails[g.metric]||0)+1;});});$('failureList').innerHTML=Object.entries(fails).map(([k,v])=>`<li><b>${esc(k)}</b> · ${v}ケースで不通過</li>`).join('')||'<li>CPUの全数値ゲートを通過しました。</li>';const incon=c.trials.filter(t=>t.agreement.passed!==true);if(incon.length)$('failureList').innerHTML+=`<li>CPU/GPUの整合未確認 ${incon.length}ケース。未実行・不一致・閾値付近を区別して下表に表示します。</li>`;$('candidateLinks').innerHTML=Object.entries(c.links).map(([n,h])=>link(h,n+'.json')).join('');$('trialRows').innerHTML=c.trials.map(t=>{const g=t.screening,passed=g.length&&g.every(x=>x.passed===true),a=t.agreement||{},v=a.values||{},failed=g.filter(x=>x.passed===false).map(x=>`${x.metric}: ${typeof x.value==='number'?num(x.value):x.value} / ${x.operator||'>='} ${x.limit}`);if(a.passed!==true)failed.push(a.reason||a.state||'CPU/GPU整合未確認');failed.push(...agreementFailures(t));if(a.near_gate_metrics?.length)failed.push('閾値付近: '+a.near_gate_metrics.join(', '));return `<tr><td>${esc(t.domain)}<br>${esc(t.condition)} / seed ${esc(t.seed)}</td><td>${flag(!!passed,'通過','不通過')}<br>${g.filter(x=>x.passed===true).length}/${g.length}ゲート</td><td>${flag(a.passed,'成立','未確認')}<br>${esc(a.state||t.gpu_state)}</td><td>${num(t.summary.final_1s_tilt_rms_deg)} → ${num(t.gpu_summary.final_1s_tilt_rms_deg)}</td><td>${num(v.tilt_rmse_deg)} / ${num(v.omega_rmse_deg_s,3)} / ${num(v.pivot_position_rmse_mm,3)}</td><td>${num(t.summary.simulated_duration_s,2)}<br>GPU ${num(t.gpu_summary.simulated_duration_s,2)}</td><td>${failed.map(esc).join('<br>')||'—'}</td></tr>`;}).join('');replayIndex=0;frameIndex=0;playing=false;$('playButton').textContent='再生';$('replaySelect').innerHTML=c.replays.map((r,i)=>`<option value="${i}">${esc(r.case)}${r.failed?' / 失敗':''}</option>`).join('');$('replayCaption').textContent=c.replays.length?'保存済みCPUの位置・quaternionから再生。代表ケースを最大3件、姿勢サンプルを最大約220点に間引いて表示。形状は模式図で、実機映像ではありません。':'この構成には保存済み姿勢framesがありません。模式的な運動は補いません。';drawReplay();}
function traceTotal(key){return allTraces.reduce((sum,t)=>sum+(t.response?.usage?.[key]||0),0);}
$('endpoint').textContent=[...new Set(allTraces.map(t=>t.request?.url).filter(Boolean))].join('\n')||'API要求traceがありません。manifestを確認してください。';const first=allTraces[0]?.request||{};$('llmOptions').innerHTML=kv('要求モデル',esc(models.join(', ')||'未記録'))+kv('応答モデル',esc(served.join(', ')||'未記録'))+kv('temperature',esc(first.temperature))+kv('出力token上限',esc(first.max_tokens))+kv('thinking / budget',`${esc(first.think)} / ${esc(first.thinking_token_budget)}`)+kv('入力token数 / window',`${esc(first.prompt_token_count)} / ${esc(first.context_window)}`)+kv('入力長の確認方式',esc(first.prompt_fit_method))+kv('HTTP timeout',`${esc(first.api_timeout_seconds)} s`)+kv('入力 / 出力tokens 合計',`${traceTotal('prompt_tokens')} / ${traceTotal('completion_tokens')}`)+kv('要求時間 合計',`${num(allTraces.reduce((s,t)=>s+(t.wall_seconds||0),0),1)} s`);
$('traceRows').innerHTML=allTraces.map(t=>`<tr><td>${t.round!==null?'R'+t.round:'対応未特定'}<br><span class="mono">${esc((t.request_id||'').slice(0,12))}</span></td><td>${esc(t.response?.model||t.request?.model)}<br>${esc(t.response?.finish_reason)}<br><span class="sub">T=${esc(t.request?.temperature)} / max=${esc(t.request?.max_tokens)} / think=${esc(t.request?.think)}:${esc(t.request?.thinking_token_budget)}</span></td><td class="num">${esc(t.request?.prompt_char_count)}文字<br>${esc(t.request?.prompt_token_count)} tokens</td><td class="num">${esc(t.response?.usage?.prompt_tokens)} / ${esc(t.response?.usage?.completion_tokens)}</td><td class="num">${num(t.wall_seconds,2)}</td><td>${esc(t.http_status)}<br>${esc(t.status)} ${esc(t.error_type||'')}</td><td>${link(t.link,'trace.json')}</td></tr>`).join('')||'<tr><td colspan="7">この過去runにはAPI要求の詳細traceがありません。未記録のモデル名、token数、呼出し時間を補いません。</td></tr>';
$('traceLimit').textContent=allTraces.length?'prompt文字数とSHA-256は、コンテキスト長に合わせて実際に送信した文字列の値です。モデルの応答に含まれるusageを保存しています。非公開思考本文、APIキー、認証ヘッダーをHTMLへ埋め込みません。round対応は送信prompt内の方針revisionで確認できたものだけです。':'過去runの詳細な推論ログはありません。提案JSONとprompt-dataを出典とし、実行オプションを推測で補いません。';
$('manifest').textContent=Object.keys(D.manifest).length?JSON.stringify(D.manifest,null,2):'このrunにはexecution-manifest.jsonがありません。';
const allocation=D.manifest.gpu_assignment||{};$('serverAssignment').innerHTML=Object.entries(allocation).map(([role,ids])=>`<div><b>${esc(role==='simulation'?'MJX指定GPU':role==='llm'?'LLM指定GPU':role)}</b>${esc(Array.isArray(ids)?ids.join(', '):JSON.stringify(ids))}</div>`).join('')+`<div><b>MJX実行の記録あり</b>${esc(gpuIds.join(', ')||'なし')}</div>`;
const colors=['#236b8d','#cb7937','#247f6c','#8f5996','#b24b56','#6b7e36','#7c9ba9','#a58b49'],T=D.telemetry||[],devices=[...new Set(T.map(r=>r.gpu))].sort();
function gpuSeries(){return devices.map((id,i)=>({values:T.filter(t=>t.gpu===id).map(t=>t.utilization),color:colors[i%colors.length]}));}
function drawGPU(){const count=Math.max(0,...devices.map(id=>T.filter(t=>t.gpu===id).length));chart($('gpuChart'),gpuSeries(),{min:0,max:100,xlabels:Array.from({length:count},(_,i)=>String(i+1)),empty:'GPU使用率の時系列はこのrunに記録されていません。'});}
$('gpuLegend').innerHTML=devices.map((id,i)=>`<span><i style="background:${colors[i%colors.length]}"></i>GPU ${esc(id)}</span>`).join('');
$('telemetryRows').innerHTML=devices.map(id=>{const rows=T.filter(t=>t.gpu===id),u=rows.map(t=>t.utilization).filter(v=>typeof v==='number'),m=rows.map(t=>t.memory_mib).filter(v=>typeof v==='number'),p=rows.map(t=>t.power_w).filter(v=>typeof v==='number');return `<tr><td>GPU ${esc(id)}</td><td>${rows.length}</td><td>${u.length?num(u.reduce((s,v)=>s+v,0)/u.length,1)+' / '+num(Math.max(...u),1):'—'}</td><td>${m.length?num(Math.max(...m),0):'—'}</td><td>${p.length?num(Math.max(...p),1):'—'}</td></tr>`;}).join('')||'<tr><td colspan="5">使用率は未記録です。割当てを実測使用率として表示しません。</td></tr>';
$('telemetrySummary').textContent=T.length?`${devices.length}GPUの${T.length}観測値。${T[0].time} → ${T.at(-1).time}。横軸は保存された観測順、縦軸は使用率%。サーバー上の他処理を含む可能性があります。`:'GPU workerの割当ては上の各構成欄で確認できます。';
$('gateRows').innerHTML=(D.contract.screening?.criteria||[]).map(g=>`<tr><td>${esc(g.metric)}</td><td>${esc(g.operator)} ${esc(g.limit)}</td><td>${esc(g.unit)}</td></tr>`).join('')+`<tr><td>required_duration_s</td><td>≥ ${esc(D.contract.screening?.required_duration_s)}</td><td>s</td></tr>`;
$('sources').innerHTML=D.sources.map(s=>link(s.href,s.name)).join('');$('sourceHashes').textContent=D.sources.map(s=>s.name+'\n'+s.sha256).join('\n\n');$('ssotFacts').textContent=`環境snapshot digest: ${S.environment?.snapshot_digest||'未記録'}。未同期のoutboxが残っている場合は、記録完了と区別してください。同期状況: ${JSON.stringify(S.onepiece_sync||{})}`;$('footer').textContent=`生成 ${D.generated_at} / ${D.run_directory} / 外部CDN・推論・計測を使わず、保存済み成果物を表示するHTMLです。`;

// A compact CPU-pose viewer: body-local cube/wheel geometry transformed by the
// saved quaternion. There is no generated or extrapolated motion.
function rotate(v,q){const [w,x,y,z]=q,[a,b,c]=v;return [(1-2*y*y-2*z*z)*a+(2*x*y-2*z*w)*b+(2*x*z+2*y*w)*c,(2*x*y+2*z*w)*a+(1-2*x*x-2*z*z)*b+(2*y*z-2*x*w)*c,(2*x*z-2*y*w)*a+(2*y*z+2*x*w)*b+(1-2*x*x-2*y*y)*c];}
function drawReplay(){const canvas=$('replayCanvas'),box=canvas.getBoundingClientRect(),w=Math.max(250,box.width),h=box.height||315,dpr=window.devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;const x=canvas.getContext('2d');x.scale(dpr,dpr);x.fillStyle='#102b3c';x.fillRect(0,0,w,h);const c=C[candidateIndex],replay=c?.replays?.[replayIndex];if(!replay?.frames?.length){x.fillStyle='#c0d1d8';x.font='12px system-ui';x.fillText('保存済み姿勢framesなし',24,h/2);$('replayTime').textContent='—';return;}frameIndex=Math.max(0,Math.min(frameIndex,replay.frames.length-1));const f=replay.frames[frameIndex],side=c.physics.cube_side_m||.18,q=f.quaternion_wxyz,p=f.position_m,scale=Math.min(w*.72,h*.74)/side,center=[w*.5,h*.75];const project=v=>[center[0]+(v[0]-v[1])*.69*scale,center[1]+((v[0]+v[1])*.29-v[2]*.88)*scale];const world=v=>{const r=rotate(v,q);return r.map((a,i)=>a+p[i]);};function line(a,b,color,width=1){x.strokeStyle=color;x.lineWidth=width;x.beginPath();x.moveTo(...project(a));x.lineTo(...project(b));x.stroke();}for(let i=-4;i<=4;i++){const d=i*side/2;line([-side*2,d,0],[side*2,d,0],'#294250');line([d,-side*2,0],[d,side*2,0],'#294250');}const vertices=[];for(let a=0;a<=1;a++)for(let b=0;b<=1;b++)for(let d=0;d<=1;d++)vertices.push(world([a*side,b*side,d*side]));const edges=[];for(let i=0;i<8;i++)for(let j=i+1;j<8;j++){const xor=i^j;if(xor===1||xor===2||xor===4)edges.push([i,j]);}edges.forEach(([i,j])=>line(vertices[i],vertices[j],'#bad8df',1.7));const radius=c.physics.wheel_radius_m||side*.28;Array.from({length:3},(_,axis)=>{const center=[side/2,side/2,side/2];center[axis]=c.physics.wheel_mount_side==='near_corner_000'?c.physics.wheel_face_inset_m:side-c.physics.wheel_face_inset_m;return center;}).forEach((origin,axis)=>{const indices=[0,1,2].filter(i=>i!==axis),angle=f.wheel_angle_rad?.[axis]||0;let previous=null;for(let k=0;k<=40;k++){const a=k*Math.PI/20,v=origin.slice();v[indices[0]]+=Math.cos(a)*radius;v[indices[1]]+=Math.sin(a)*radius;const point=world(v);if(previous)line(previous,point,['#df9863','#7bbfa9','#67a8ca'][axis],2.5);previous=point;}const spoke=origin.slice();spoke[indices[0]]+=Math.cos(angle)*radius;spoke[indices[1]]+=Math.sin(angle)*radius;line(world(origin),world(spoke),'#eff8ee',1.2);});x.fillStyle='#d8e7ea';x.font='11px system-ui';x.fillText(`CPU姿勢  t=${num(f.time_s,3)} s   tilt=${num(f.tilt_total_deg,3)}°`,16,24);x.fillStyle='#9ab7c1';x.fillText(`pivot=${num(f.pivot_displacement_mm,3)} mm / 保存姿勢の模式表示`,16,43);$('replaySlider').max=String(replay.frames.length-1);$('replaySlider').value=String(frameIndex);$('replayTime').textContent=num(f.time_s,2)+'s';}
$('replaySelect').addEventListener('change',e=>{replayIndex=Number(e.target.value);frameIndex=0;drawReplay();});$('replaySlider').addEventListener('input',e=>{frameIndex=Number(e.target.value);playing=false;$('playButton').textContent='再生';drawReplay();});$('playButton').addEventListener('click',()=>{playing=!playing;$('playButton').textContent=playing?'一時停止':'再生';lastAnimation=0;});
function animate(t){if(playing){const frames=C[candidateIndex]?.replays?.[replayIndex]?.frames;if(frames?.length){const dt=frameIndex+1<frames.length?Math.max(15,(frames[frameIndex+1].time_s-frames[frameIndex].time_s)*1000):40;if(!lastAnimation||t-lastAnimation>=dt){frameIndex=(frameIndex+1)%frames.length;drawReplay();lastAnimation=t;}}}requestAnimationFrame(animate);}requestAnimationFrame(animate);
window.addEventListener('resize',()=>{drawScores();drawGPU();drawReplay();});if(R.length)selectRound(0);else if(C.length)selectCandidate(0);drawScores();drawGPU();drawReplay();
</script></body></html>'''


def build_report(run_dir, output=None):
    root = Path(run_dir).resolve()
    destination = Path(output).resolve() if output else root / "memory-pipeline-report.html"
    data = collect(root, destination)
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # Data may include a proposal string containing HTML. Never let it terminate
    # the inert JSON script element or execute markup in the report.
    embedded = embedded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_HTML.replace("__DATA__", embedded), encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Saved balancing_cube run directory")
    parser.add_argument("--output", help="HTML destination (default: run-dir/memory-pipeline-report.html)")
    args = parser.parse_args()
    print(build_report(args.run_dir, args.output))


if __name__ == "__main__":
    main()

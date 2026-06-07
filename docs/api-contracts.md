# API 契約 — SimulatorProtocol とイベントログ

リビングドキュメント。プロトコル、エージェントモード、ログスキーマ変更時に更新する。

## SimulatorProtocol

実装: `StationSimulator`（ECLSS + EPS、シナリオのデフォルト）、`MockEclssSimulator`（プラントのみ）、`SsosAdapter`（将来）。

| メソッド | 戻り値 | 説明 |
| --- | --- | --- |
| `step()` | `TelemetrySnapshot` | 物理を 1 ティック進める |
| `apply_command(cmd)` | `CommandResult` | 一時的な回復アクション |
| `apply_design_change(change)` | `DesignState` | 恒久トポロジ/パラメータ変更 |
| `get_topology()` | `TopologyGraph` | 現在のノード/エッジグラフ |
| `get_design_parameters()` | `dict[str, float]` | 可変設計パラメータ |
| `get_design_state()` | `DesignState` | トポロジ + パラメータのスナップショット |
| `inject_anomaly(spec)` | `None` | 複合異常をスケジュール |

### TelemetrySnapshot

```json
{
  "step": 20,
  "co2_ppm": 1240.5,
  "scrubber_efficiency": 0.72,
  "power_margin_w": 45.0,
  "fan_speed": 0.7,
  "bypass_enabled": false,
  "load_reduced": false,
  "eps_support_w": 120.0,
  "eps_support_steps_remaining": 4,
  "anomaly_flags": ["scrubber_degradation"]
}
```

### RecoveryCommand

```json
{
  "kind": "set_fan_speed",
  "value": 1.0,
  "issued_by": "operator"
}
```

サポートする `kind`: `set_fan_speed`、`enable_bypass`、`reduce_load`、`request_eps_boost`。

### DesignChange

```json
{
  "kind": "add_edge",
  "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
  "proposed_by": "design_engineer"
}
```

サポートする `kind`: `add_edge`、`set_parameter`。

### ヘルス閾値

| 指標 | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 1000 | 1000–2000 | ≥ 2000 |
| 電力マージン (W) | > 0 | 0 〜 −100 | ≤ −100 |

## エージェントモード

`src/scenario/scrubber_degradation/scenario.yaml` の `agents.mode` で設定。ロール閾値は `agents.yaml`。

| `agents.mode` | チーム | アクションの出所 | メッセージ |
| --- | --- | --- | --- |
| `none` | — | — | — |
| `labeled` | `ScrubberDegradationTeam` | ルール | ルールメッセージのみ |
| `llm` | 同上 | LLM のみ（policy 非参照） | `llm` / `llm_parse_fail` / `llm_no_action` |

将来: `base`（ラベルなし創発ロール）— [memo/backlog.md](../memo/backlog.md) BL-001。

### llm のメタデータ

`messages.jsonl` の LLM メッセージに付与される任意フィールド:

| フィールド | 例 | 説明 |
| --- | --- | --- |
| `deliberation_phase` | `deliberation` / `action` / `post_run_proposal` | 議論フェーズ |
| `decision_source` | `llm` / `llm_parse_fail` / `llm_no_action` | 最終決定の出所 |
| `parse_status` | `ok` / `parse_error` | JSON パース結果 |
| `parse_error` | 文字列または `null` | パース失敗時の詳細 |
| `raw_response_excerpt` | 文字列 | デバッグ用の生応答抜粋 |

`from_role` は `engineer_1` .. `engineer_N`。Persona 本文・`policy` 閾値はログに含めない。Situation は `### Telemetry` + `### World state` のみ。

## ROS2 風トピック（`environment/ssos/topics.py`）

| トピック | 方向 | ペイロード |
| --- | --- | --- |
| `/eclss/telemetry/co2_ppm` | pub | float |
| `/eclss/telemetry/scrubber_efficiency` | pub | float |
| `/eclss/telemetry/power_margin_w` | pub | float |
| `/eclss/command/set_fan_speed` | sub | float 0–1 |
| `/eclss/command/enable_bypass` | sub | bool |
| `/eclss/command/reduce_load` | sub | bool |
| `/eclss/command/request_eps_boost` | sub | float W (0, 500] |
| `/eclss/events/design_change` | event | DesignChange dict |

## ROS2 風 EPS トピック（`environment/ssos/eps_topics.py`）

[space_station_eps](https://github.com/space-station-os/space_station_os/tree/main/space_station_eps) を参考。モック: `MockSarj`、`MockBcdu`、`EpsStack`（EPS-3 で ECLSS と結合）。

| トピック | 方向 | ペイロード |
| --- | --- | --- |
| `/solar/voltage` | pub | float V（SARJ 推定） |
| `/bcdu/operation` | sub | 放電要求: `{support_w, duration_steps}` |
| `/bcdu/status` | pub | `BcduStatus` dict — `mode`、`bus_voltage_v`、`support_w`、`fault` 等 |
| `/eps/diagnostics` | pub | `EpsDiagnostics` dict |
| `/eps/eclss/load_request_w` | pub | float W（ブリッジトピック、EPS-3） |

**BCDU `mode`**: `idle`、`charging`、`discharging`、`fault`、`safe`。

**放電契約**（`MockBcdu.request_discharge`）: `support_w` は (0, 500]、`duration_steps` ≥ 1、バス電圧 [70, 120] V。fault 時は `fault` にラッチし、以降の放電要求は失敗。

## JSONL イベントストリーム

全実行は `src/experiments/results/<run_id>/` に書き込む。

### messages.jsonl

`agents.mode` が `labeled` または `llm` のとき出力。

**ルールメッセージ:**

```json
{
  "step": 33,
  "from_role": "engineer_2",
  "to_role": "team",
  "message": "CO2 at 1016 ppm exceeds alert threshold 900.",
  "message_type": "alert",
  "reasoning": "Telemetry threshold crossed.",
  "decision_source": "rule"
}
```

**LLM メッセージ**（`llm`）:

```json
{
  "step": 33,
  "from_role": "engineer_1",
  "to_role": "team",
  "message": "...",
  "message_type": "recovery_command",
  "reasoning": "...",
  "decision_source": "llm",
  "deliberation_phase": "action",
  "parse_status": "ok",
  "parse_error": null,
  "raw_response_excerpt": "..."
}
```

`message_type`:

| 種別 | 出所 |
| --- | --- |
| `alert`、`diagnosis`、`recovery_command`、`design_change` | ルールまたは LLM ガード |

### telemetry.jsonl

ステップごとの生物理スナップショット（`TelemetrySnapshot` と同フィールド）。

### health_metrics.jsonl

```json
{"step": 5, "co2_status": "safe", "power_status": "safe", "overall": "safe"}
```

### eps_telemetry.jsonl

`mock_station` 実行時（EPS-4）。SARJ + BCDU から 1 行/ステップ。

```json
{
  "step": 22,
  "solar_voltage_v": 113.14,
  "beta_angle_deg": 45.0,
  "in_eclipse": false,
  "bcdu_mode": "discharging",
  "bus_voltage_v": 110.0,
  "support_w": 120.0,
  "support_steps_remaining": 3,
  "fault": false,
  "fault_message": ""
}
```

### events.jsonl

異常、回復コマンド、設計変更。

```json
{"step": 20, "kind": "/eclss/events/anomaly", "flags": ["scrubber_degradation"]}
{"step": 33, "kind": "/eclss/events/recovery_applied", "command": {"kind": "set_fan_speed", "value": 1.0, "issued_by": "operator"}, "message": "fan_speed set to 1.0"}
{"step": 35, "kind": "/eclss/events/design_change", "change": {"kind": "add_edge", "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}, "proposed_by": "design_engineer"}}
```

### design_state.jsonl

各ステップのエージェント行動**前**のトポロジ + パラメータスナップショット。

```json
{
  "step": 36,
  "topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}, "..."],
    "edges": [
      {"source": "manifold", "target": "scrubber", "kind": "flow"},
      {"source": "manifold", "target": "scrubber", "kind": "bypass"}
    ]
  },
  "parameters": {"scrubber_base_efficiency": 0.95, "...": "..."}
}
```

ステップ *N* で設計変更イベントがあれば、step *N* と *N+1* を比較する。

### summary.json

実行終了時に 1 回書き込む KPI。

```json
{
  "scenario": "scrubber_degradation",
  "simulator": "mock_station",
  "agents_mode": "labeled",
  "steps": 50,
  "peak_co2_ppm": 1016.34,
  "final_co2_ppm": 967.2,
  "final_power_margin_w": -42.5,
  "min_power_margin_w": -128.0,
  "eps_boost_applied_step": 28,
  "power_recovered_above_critical_step": 32,
  "final_health": {"step": 50, "co2_status": "safe", "power_status": "warning", "overall": "warning"},
  "anomaly_seen": true,
  "co2_above_threshold_step": 33,
  "co2_recovered_below_threshold_step": 40,
  "message_count": 59,
  "design_change_count": 1,
  "provenance_path": "src/experiments/results/scrubber_degradation_labeled/provenance.jsonl",
  "provenance_record_count": 2
}
```

### provenance.jsonl（Day 5B+ / EPS-4）

One Piece 互換 provenance: **設計変更**と **EPS 回復**（`request_eps_boost`）。

```json
{
  "record_id": "scrubber_degradation_labeled:design_change:1",
  "run_id": "scrubber_degradation_labeled",
  "scenario": "scrubber_degradation",
  "step": 35,
  "actor": "design_engineer",
  "actor_kind": "ai_agent",
  "change_kind": "add_edge",
  "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
  "before_topology": {"nodes": [{"id": "cabin"}], "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]},
  "after_topology": {"nodes": [{"id": "cabin"}], "edges": [{"source": "manifold", "target": "scrubber", "kind": "bypass"}]},
  "trace": {"event_kind": "/eclss/events/design_change", "decision_source": "rule"}
}
```

**回復レコード**（`record_type: recovery`）:

```json
{
  "record_id": "scrubber_degradation_labeled:recovery:2",
  "record_type": "recovery",
  "change_kind": "request_eps_boost",
  "step": 28,
  "actor": "operator",
  "payload": {"support_w": 120.0, "eps": {"bcdu_mode": "discharging"}},
  "trace": {"event_kind": "/eclss/events/recovery_applied", "decision_source": "rule"}
}
```

## シナリオの実行

```bash
# ベースライン（agents.mode: none）— scenario.yaml のデフォルト
python src/scripts/run_mock_eclss.py

# ルールベース labeled チーム
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled'}})"

# Persona + 2ラウンド議論 + ガード付き LLM（Ollama 要）
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}})"
```

プログラムからの回復スモークテスト:

```python
from environment.protocol import CommandKind, RecoveryCommand
from environment.ssos import StationSimulator, MockEclssSimulator

station = StationSimulator(MockEclssSimulator())
station.apply_command(RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=120.0))
```

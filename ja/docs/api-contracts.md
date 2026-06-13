# API 契約 — SimulatorProtocol とイベントログ

**ECLSS**（Environmental Control and Life Support System / 生命維持装置）と **EPS**（Electrical Power System / 電力系）のシミュレータ境界、回復コマンド、JSONL スキーマのリファレンス。プロトコルやログ形式を変更したら **本ドキュメントを同時に更新**する。

> シナリオの叙事: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md)

---

## SimulatorProtocol

実装:

| クラス | 用途 |
| --- | --- |
| `StationSimulator` | **デフォルト** — ECLSS + EPS |
| `MockEclssSimulator` | プラントのみ（単体テスト） |
| `SsosAdapter` | 将来の実 SSOS ブリッジ（スタブ） |

| メソッド | 戻り値 | 説明 |
| --- | --- | --- |
| `step()` | `TelemetrySnapshot` | 生命維持プラントを 1 ティック進める |
| `apply_command(cmd)` | `CommandResult` | 一時的な回復アクション |
| `get_topology()` | `TopologyGraph` | ノード/エッジ |
| `get_design_parameters()` | `dict[str, float]` | 可変パラメータ |
| `get_design_state()` | `DesignState` | トポロジ + パラメータ |
| `inject_anomaly(spec)` | `None` | 異常スケジュール |

---

## TelemetrySnapshot

`telemetry.jsonl` の 1 行。

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

| フィールド | 説明 |
| --- | --- |
| `co2_ppm` | 居住空間 CO2 濃度 |
| `scrubber_efficiency` | 有効除去効率（異常で低下） |
| `power_margin_w` | ECLSS ネット電力マージン（正=余裕、負=不足） |
| `eps_support_w` | EPS からの一時支援ワット |
| `eps_support_steps_remaining` | 支援残り step 数 |
| `anomaly_flags` | 有効な異常名のリスト |

---

## RecoveryCommand

ランタイムで `apply_command` される一時操作。

```json
{
  "kind": "set_fan_speed",
  "value": 1.0,
  "issued_by": "engineer_2"
}
```

| `kind` | `value` 型 | 説明 |
| --- | --- | --- |
| `set_fan_speed` | float 0–1 | ファン速度 |
| `enable_bypass` | bool | 一時バイパス有効化 |
| `reduce_load` | bool | 代謝負荷削減 |
| `request_eps_boost` | float W (0, 500] | EPS 放電支援要求 |

`issued_by` は代表エンジニア ID（`engineer_*`）またはレガシー `operator`。

---

## design_proposals.json（scrubber_degradation 専用・凍結）

ラン終了後に 1 ファイル。シミュレーション結果のトポロジは**変更されない**。ダッシュボードが dict を直接解釈して After プレビューを描画する（`DesignStateManager.apply_dict_change` と同等ロジック）。

| `change_kind` | 用途 |
| --- | --- |
| `add_edge` | 新規エッジ（flow / bypass / power） |
| `add_node` | 新規ノード（valve、electrical 等） |
| `set_parameter` | 設計パラメータ変更 |

**ランタイム `apply_design_change` は Phase 0 で削除済み。** 恒久変更はラン中に適用しない。

---

## operational_proposals.json（ssos_eclss_loop 予定）

新シナリオ `ssos_eclss_loop` 向け。トポロジ変更なし。次ラン入力として適用:

| `change_kind` | 用途 |
| --- | --- |
| `set_parameter` | 起動時 YAML パラメータ（`ARS.yaml` 等） |
| `action_profile` | 既存 Action goal フィールド・頻度 |
| `service_config` | 既存 Service 呼び出し量・間隔 |

詳細: [memo/ssos_eclss_loop_connection_plan.md](../memo/ssos_eclss_loop_connection_plan.md)

---

## design_proposals.json スキーマ例

```json
{
  "proposed_by": "engineer_2",
  "decision_source": "rule",
  "message": "Propose permanent bypass plumbing between manifold and scrubber.",
  "reasoning": "Repeated anomaly and high CO2 during the run; ...",
  "changes": [
    {
      "change_kind": "add_edge",
      "payload": {
        "node_a": "manifold",
        "node_b": "scrubber",
        "kind": "bypass"
      }
    }
  ],
  "baseline_topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}, "..."],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}, "..."]
  },
  "parse_notes": []
}
```

| フィールド | 説明 |
| --- | --- |
| `proposed_by` | 最終 step の action rep |
| `decision_source` | `rule` または `llm` |
| `changes` | 提案された恒久変更のリスト |
| `baseline_topology` | ラン終了時点のグラフ（変更前） |
| `parse_notes` | LLM パース時の警告（任意） |

`summary.json` の `design_proposals_path`、`design_proposal_count` と対応。

---

## ヘルス閾値

`health_metrics.jsonl` — `compute_health_metrics()`（`src/environment/eclss_ops/telemetry.py`）:

```json
{"step": 5, "co2_status": "safe", "power_status": "safe", "overall": "safe"}
```

| 定数 | 値 |
| --- | --- |
| `CO2_SAFE_PPM` | 800 |
| `CO2_WARNING_PPM` | 1200 |
| `POWER_LOW_W` | 0 |
| `POWER_CRITICAL_W` | −150 |

| 指標 | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 800 | 800 〜 1200 未満 | ≥ 1200 |
| 電力マージン (W) | > 0 | 0 〜 −150 未満 | ≤ −150 |
| `overall` | 両方 safe | より悪い方が warning | より悪い方が critical |

エージェントの `policy.co2_recovery_ppm`（デフォルト 1000）などは**回復コマンドのトリガー**であり、上表のヘルス区分とは別。

---

## エージェントモード

| `agents.mode` | チーム | メッセージ | ランタイムコマンド | 事後提案 |
| --- | --- | --- | --- | --- |
| `none` | — | — | — | — |
| `labeled_rule_base` | `ScrubberDegradationTeam` | `decision_source: rule` | policy 駆動 | rule |
| `llm` | 同上 | `llm` / `llm_parse_fail` / `llm_no_action` | LLM `commands` | llm |

将来: `base`（創発ロール）— [memo/backlog.md](../memo/backlog.md) BL-001。

### messages.jsonl — ルール例

```json
{
  "step": 33,
  "from_role": "engineer_2",
  "to_role": "team",
  "message": "CO2 at 1016 ppm exceeds recovery band 1000 ppm.",
  "message_type": "alert",
  "reasoning": "Telemetry threshold crossed.",
  "decision_source": "rule"
}
```

### messages.jsonl — LLM 例

```json
{
  "step": 17,
  "from_role": "engineer_1",
  "to_role": "team",
  "message": "EPS boost critical for CO2 reduction.",
  "message_type": "recovery_command",
  "reasoning": "Power margin remains low, bypass ineffective.",
  "decision_source": "llm",
  "deliberation_phase": "action",
  "parse_status": "ok",
  "parse_error": null,
  "raw_response_excerpt": "{...}"
}
```

| `message_type` | 説明 |
| --- | --- |
| `alert` | 閾値超過通知 |
| `diagnosis` | 異常フラグに基づく所見 |
| `recovery_command` | 回復判断の説明 |
| `comment` | llm deliberation の発言 |
| `skip` | パース失敗・空 action（`llm_no_action` 等） |

| `deliberation_phase` | 説明 |
| --- | --- |
| `deliberation` | 全員議論ラウンド |
| `action` | 代表のコマンド決定 |
| `post_run_proposal` | 事後設計（messages に載る場合） |

`from_role` は `engineer_1` … `engineer_N`。Persona 全文や `policy` 値はログに含めない。

---

## ROS2 風 ECLSS トピック

`environment/ssos/topics.py` — モック／将来アダプタの契約。

| トピック | 方向 | ペイロード |
| --- | --- | --- |
| `/eclss/telemetry/co2_ppm` | pub | float |
| `/eclss/telemetry/scrubber_efficiency` | pub | float |
| `/eclss/telemetry/power_margin_w` | pub | float |
| `/eclss/command/set_fan_speed` | sub | float 0–1 |
| `/eclss/command/enable_bypass` | sub | bool |
| `/eclss/command/reduce_load` | sub | bool |
| `/eclss/command/request_eps_boost` | sub | float W |
| `/eclss/events/design_change` | event | **レガシー** — ランタイム発行なし（scrubber 過去 run 互換） |
| `/eclss/events/recovery_applied` | event | コマンド適用結果 |
| `/eclss/events/anomaly` | event | 異常フラグ |

---

## ROS2 風 EPS トピック

**EPS**（Electrical Power System）— 発電・蓄電・配電。MVP では **SARJ**（Solar Alpha Rotary Joint）と **BCDU**（Battery Charge/Discharge Unit）をモック。実系では **MBSU**（Main Bus Switching Unit）、**DDCU**（Direct Current-to-Direct Current Converter Unit）も含まれる。

`environment/ssos/eps_topics.py`。参考: [space_station_eps](https://github.com/space-station-os/space_station_os/tree/main/space_station_eps)。

| トピック | 方向 | ペイロード |
| --- | --- | --- |
| `/solar/voltage` | pub | float V |
| `/bcdu/operation` | sub | `{support_w, duration_steps}` |
| `/bcdu/status` | pub | `BcduStatus` |
| `/eps/diagnostics` | pub | `EpsDiagnostics` |
| `/eps/eclss/load_request_w` | pub | float W |

**BCDU `mode`**: `idle`、`charging`、`discharging`、`fault`、`safe`。

---

## JSONL 出力ディレクトリ

`src/experiments/results/<run_id>/`

### events.jsonl

```json
{"step": 20, "kind": "/eclss/events/anomaly", "flags": ["scrubber_degradation"]}
{"step": 33, "kind": "/eclss/events/recovery_applied", "command": {"kind": "set_fan_speed", "value": 1.0, "issued_by": "engineer_2"}, "message": "fan_speed set to 1.0"}
```

現行フローでは **`/eclss/events/design_change` はランタイムに発生しない**（事後提案は `design_proposals.json`）。

### design_state.jsonl

毎 step、エージェント行動**前**のスナップショット。ランタイム中トポロジ不変のため `topology` は run 全体で同一。

```json
{
  "step": 36,
  "topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]
  },
  "parameters": {"scrubber_base_efficiency": 0.95}
}
```

### eps_telemetry.jsonl

`StationSimulator` 実行時のみ。1 行/step。

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

### summary.json

```json
{
  "scenario": "scrubber_degradation",
  "simulator": "mock_station",
  "agents_mode": "labeled_rule_base",
  "team_count": 4,
  "agent_ids": ["engineer_1", "engineer_2", "engineer_3", "engineer_4"],
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
  "design_change_count": 0,
  "design_proposal_count": 1,
  "design_proposals_path": "src/experiments/results/.../design_proposals.json",
  "provenance_path": "src/experiments/results/.../provenance.jsonl",
  "provenance_record_count": 2
}
```

---

## provenance.jsonl（One Piece 互換）

`src/integrations/one_piece/client.py` が run 終了時に生成。

### 現状エクスポートされるもの

| ソース | 条件 |
| --- | --- |
| ランタイム `design_change` イベント | 現シナリオでは **0 件** |
| `request_eps_boost` 回復 | `events.jsonl` の `recovery_applied` |

### 回復レコード例

```json
{
  "record_id": "scrubber_degradation_labeled_rule_base:recovery:1",
  "record_type": "recovery",
  "run_id": "scrubber_degradation_labeled_rule_base",
  "scenario": "scrubber_degradation",
  "step": 28,
  "actor": "engineer_3",
  "actor_kind": "ai_agent",
  "change_kind": "request_eps_boost",
  "payload": {"support_w": 120.0, "eps": {"bcdu_mode": "discharging"}},
  "trace": {
    "event_kind": "/eclss/events/recovery_applied",
    "decision_source": "rule",
    "message": "Requesting EPS support boost of 120 W."
  }
}
```

### 未エクスポート（開発予定）

`design_proposals.json` の事後提案 → provenance レコード。詳細: [one-piece-integration.md](one-piece-integration.md)、[development-plan.md](development-plan.md)。

スキーマ参照: `src/integrations/one_piece/ssot_schema.json`。

---

## 実行例

```bash
pip install -e ".[dev]"

# ベースライン
python src/scripts/run_mock_eclss.py

# labeled_rule_base
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}})"

# llm（Ollama 要）
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}})"
```

プログラムからの EPS スモーク:

```python
from environment.protocol import CommandKind, RecoveryCommand
from environment.ssos import StationSimulator, MockEclssSimulator

station = StationSimulator(MockEclssSimulator())
station.apply_command(RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=120.0))
```

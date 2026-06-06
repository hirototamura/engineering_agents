# シナリオ: scrubber_degradation

ECLSS 仮想運用レジリエンス・ループ MVP の参照シナリオ。

## 叙事（フェーズ）ルールベースの場合


| フェーズ | ステップ  | 内容                                            |
| ---- | ----- | --------------------------------------------- |
| 均衡   | 1–19  | CO2 約 800 ppm、スクラバーはベースライン効率                  |
| 異常   | 20+   | `scrubber_degradation`: 効率低下、電力マージン縮小、CO2 産生増 |
| 危険帯  | 約 33+ | CO2 が 1000 ppm 超（ベースライン / labeled 実行）         |
| 対応   | 33–40 | Operator 回復コマンド（ファン、負荷削減、バイパス）                |
| 設計変更 | ≥35   | DesignEngineer が恒久 bypass エッジを追加（labeled モード） |
| 回復   | 約 40+ | CO2 が 1000 ppm 未満へ（labeled モード）               |


物理のみ（`agents.mode: none`）は異常と CO2 上昇を示すが、**回復・設計変更は行わない**。

## 設定ファイル


| ファイル                                                                | 用途                                                   |
| ------------------------------------------------------------------- | ---------------------------------------------------- |
| [scenario.yaml](../src/scenario/scrubber_degradation/scenario.yaml) | ステップ数、初期状態、設計パラメータ、異常、`agents.mode`、run ID           |
| [agents.yaml](../src/scenario/scrubber_degradation/agents.yaml)     | Persona、メモリ設定、ルール閾値、LLM 設定（`agents.mode` ≠ `none` 時） |


### 主要シミュレーションパラメータ

- 初期 CO2: 800 ppm
- 異常開始: step 20
- スクラバー効率減衰: 異常後 0.02 / step
- 異常時 CO2 産生倍率: 1.4×

### エージェントモード

```yaml
# scenario.yaml
agents:
  mode: none  # none | labeled | labeled_llm_guarded
```

実行時オーバーライド:

```python
from scenario.runner import run_scenario

run_scenario("scrubber_degradation", overrides={"agents": {"mode": "labeled"}})
```

## Labeled ロール（ルール fallback）

シナリオ固有 — 新チームクラスなしでは他シナリオに流用しない。


| ロール            | 設定キー                                           | 挙動                               |
| -------------- | ---------------------------------------------- | -------------------------------- |
| Monitor        | `roles.monitor.co2_alert_ppm`（900）             | CO2 高時に `alert`                  |
| Diagnostician  | —                                              | 異常フラグ時に `diagnosis`              |
| Operator       | `co2_recovery_ppm`、`fan_speed`、`eps_boost_w` 等 | 回復コマンド（電力 critical 時 EPS ブースト含む） |
| DesignEngineer | `min_step`、`bypass_edge`                       | `add_edge` バイパスを提案               |


研究メモ: ラベルは人間の分業慣習の写し。ラベルなし創発ロールは [memo/backlog.md](../memo/backlog.md) BL-001。

## labeled_llm_guarded モード

Persona ベースの 2 ラウンド議論（1 ステップ 8 回 LLM 呼び出し）+ ガード:


| ラウンド          | エージェント                                                                  | 出力                                       |
| ------------- | ----------------------------------------------------------------------- | ---------------------------------------- |
| 1 — オープンフォーラム | monitor, diagnostician, operator, design_engineer                       | message + reasoning（+ optional `memory`） |
| 2 — 反応 + 行動   | monitor, diagnostician（反応）；operator, design_engineer（commands / design） | 同上；action キーは Round 2 のみ                 |


**Persona とシナリオの分離**: `agents.yaml` の `personas` は専門家としての声と議論スタイルのみ。シナリオ説明・閾値・テレメトリは `## Situation`（`ScrubberDegradationTeam._situation_context()` が注入）。コマンド・設計の形は出力契約（contract）側。

**メモリ**: チーム共有 `DiscourseBuffer` + 個体私有 `AgentMemory`。`agents.yaml` の `memory_limit` / `discourse_window` を参照。

メッセージ metadata: `deliberation_phase`、`main_role`、`decision_source`（`llm`、`rule_fallback`、`llm_guard_reject`）。

parse/ガード失敗時は rule fallback。Ollama とモデル pull が必要（デフォルト `qwen3.5:2b`、`temperature: 0.45`、`max_tokens: 320`）。

## 出力の読み方

実行後、`src/experiments/results/<run_id>/` を開く:


| 知りたいこと               | ファイル                 | 見る項目                                                                      |
| -------------------- | -------------------- | ------------------------------------------------------------------------- |
| エージェントの発言            | `messages.jsonl`     | `from_role`、`message_type`、`decision_source`、`deliberation_phase`         |
| プラントの変化              | `telemetry.jsonl`    | `co2_ppm`、`scrubber_efficiency`、フラグ                                       |
| 実行されたコマンド            | `events.jsonl`       | `recovery_applied`、`design_change`                                        |
| 設計グラフ                | `design_state.jsonl` | `topology.edges` — 変更の翌ステップから bypass                                      |
| One Piece provenance | `provenance.jsonl`   | actor、change_kind、変更前後トポロジ、trace                                          |
| 実行 KPI               | `summary.json`       | `peak_co2_ppm`、`co2_recovered_below_threshold_step`、`design_change_count` |


### design_change の例

**構造化変更**（`events.jsonl`）:

```json
{"step": 35, "kind": "/eclss/events/design_change", "change": {"kind": "add_edge", "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}, "proposed_by": "design_engineer"}}
```

**人間可読な提案**（`messages.jsonl`）:

```json
{"step": 35, "from_role": "design_engineer", "message_type": "design_change", "message": "Proposing permanent bypass plumbing between manifold and scrubber.", "decision_source": "rule"}
```

**トポロジ効果**（`design_state.jsonl`）: step 35 と 36 を比較 — 新エッジ `{"source": "manifold", "target": "scrubber", "kind": "bypass"}`。

## テスト


| テスト                                           | モード                               | 検証内容                        |
| --------------------------------------------- | --------------------------------- | --------------------------- |
| `tests/scenario/test_scrubber_baseline.py`    | `none`                            | 異常発火、CO2 > 1000、エージェントなし    |
| `tests/scenario/test_scrubber_with_agents.py` | `labeled` / `labeled_llm_guarded` | 4 ロール、回復、設計変更、最終 CO2 < 1000 |


エージェント・物理コード変更時はベースラインを常に green に保つ。

## 可視化（ダッシュボード）

```bash
python -m streamlit run src/tools/dashboard/app.py
```

機能:

- 実行セレクタ（`src/experiments/results/<run_id>`）
- ステップスライダー（テレメトリ、メッセージ、イベント、provenance と同期）
- CO2 / 電力マージンのトレンド（現在ステップマーカー付き）
- 実行比較（provenance、最終設計パラメータ差分 — 例: `labeled` vs `labeled_llm_guarded`）


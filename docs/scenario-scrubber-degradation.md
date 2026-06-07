# シナリオ: scrubber_degradation

ECLSS 仮想運用レジリエンス・ループ MVP の参照シナリオ。

## 叙事（フェーズ）ルールベースの場合

| フェーズ | ステップ  | 内容                                            |
| ---- | ----- | --------------------------------------------- |
| 均衡   | 1–19  | CO2 約 800 ppm、スクラバーはベースライン効率                  |
| 異常   | 20+   | `scrubber_degradation`: 効率低下、電力マージン縮小、CO2 産生増 |
| 危険帯  | 約 33+ | CO2 が 1000 ppm 超（ベースライン / labeled 実行）         |
| 対応   | 33–40 | 代表エンジニアの回復コマンド（ファン、負荷削減、バイパス）                |
| 回復   | 約 40+ | CO2 が 1000 ppm 未満へ（labeled モード）               |

物理のみ（`agents.mode: none`）は異常と CO2 上昇を示すが、**回復・設計変更は行わない**。

## 設定ファイル

| ファイル                                                                | 用途                                                   |
| ------------------------------------------------------------------- | ---------------------------------------------------- |
| [scenario.yaml](../src/scenario/scrubber_degradation/scenario.yaml) | ステップ数、初期状態、設計パラメータ、異常、`agents.mode`、run ID           |
| [agents.yaml](../src/scenario/scrubber_degradation/agents.yaml)     | チーム構成、Persona、メモリ、`policy`（labeled 専用）、LLM 設定 |

### 主要シミュレーションパラメータ

- 初期 CO2: 800 ppm
- 異常開始: step 20
- スクラバー効率減衰: 異常後 0.02 / step
- 異常時 CO2 産生倍率: 1.4×

### エージェントモード

```yaml
# scenario.yaml
agents:
  mode: none  # none | labeled | llm
```

実行時オーバーライド:

```python
from scenario.runner import run_scenario

run_scenario("scrubber_degradation", overrides={"agents": {"mode": "labeled"}})
```

## 同種エンジニアチーム

| 設定 | 説明 |
| --- | --- |
| `team.count` | エージェント数（デフォルト 4） |
| `team.id_prefix` | ID 接頭辞（`engineer_1` .. `engineer_N`） |
| `team.persona` | 全員共通の Persona 本文 |
| `policy` | **labeled 専用** — `co2_recovery_ppm` 等の閾値 |

代表者: `engineer_{(step-1) % N}` が各 step の action rep（回復コマンド発行）。事後 design も最終 step の代表が提案。

## 初期トポロジ（デフォルト）

`environment/eclss_ops/design_state.py` の Mock ECLSS 初期グラフ:

| ノード | kind | 説明 |
| --- | --- | --- |
| `cabin` | volume | 居住空間 |
| `manifold` | manifold | 送気マニホールド |
| `scrubber` | scrubber | CO2 スクラバー |
| `power_bus` | electrical | 電力バス |

| エッジ (source → target) | kind |
| --- | --- |
| cabin → manifold | flow |
| manifold → scrubber | flow |
| scrubber → cabin | flow |
| power_bus → scrubber | power |

ランタイム中にトポロジは変更しない。**ラン終了後**に代表が `design_proposals.json` で変更点を提案する。`design_state.jsonl` はランタイムの実状態のみを記録する。

## llm モード

同種 N 体 + **1 ラウンド deliberation** + 代表 action（N+1 LLM 呼び出し/step）。**policy 非参照**（プロンプト・コードとも）。

| フェーズ | 参加者 | 出力 |
| --- | --- | --- |
| deliberation | 全 N 体 | message + reasoning（+ optional `memory`） |
| action | `engineer_{(step-1)%N}` | commands |
| 事後（ラン終了後） | 最終 step の代表 | `design_proposals.json` |

**Situation 二層化**: `### Telemetry`（定量）と `### World state`（記述的健康状態）のみ。規範判断は Persona / charter の世界モデルに委ねる。

**メモリ**: チーム共有 `DiscourseBuffer` + 個体私有 `AgentMemory`。

詳細: [memo/homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md)

## 出力と検証

| テスト | モード | 主な検証 |
| --- | --- | --- |
| `tests/scenario/test_scrubber_baseline.py` | `none` | 異常・CO2 上昇、エージェントなし |
| `tests/scenario/test_scrubber_with_agents.py` | `labeled` / `llm` | 同種チーム、回復、事後設計提案、最終 CO2 < 1000（labeled） |

## 関連ドキュメント

- [architecture.md](architecture.md) — レイヤと実行フロー
- [api-contracts.md](api-contracts.md) — JSONL スキーマ
- [memo/backlog.md](../memo/backlog.md) — BL-002 進化ペルソナ

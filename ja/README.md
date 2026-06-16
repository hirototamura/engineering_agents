# Engineering Agents — ECLSS レジリエンス・ループ

> English: [../en/README.md](../en/README.md)

**ECLSS**（Environmental Control and Life Support System / 環境制御・生命維持システム）の異常に対し、**エージェントチームが検知・対応し、事後に設計変更を提案する**までをシミュレートする研究用リポジトリです。ECLSS は物理実験装置ではなく、乗員の生存に必要な**生命維持装置**を指します。

本リポジトリの `engineering_agents` は、将来の宇宙ステーション運用ソフトウェア（**Space Station OS / SSOS**）を**モックしたシミュレータ**上で動作します。生命維持プラント（ECLSS）と電力系（**EPS** / Electrical Power System）を Python で再現し、ROS2 風トピック契約に沿った API でエージェントと接続します。**実機 SSOS や軌道上システムへの接続は行いません。**

自律的なハードウェア設計の**一つ手前**として、「運用中の異常 → チームの判断 → 恒久設計の提案」というループを検証するのが目的です。

---

## 一目でわかる（ダッシュボード）

シミュレーション結果は JSONL に記録され、[Streamlit ダッシュボード](#ダッシュボード) で次の 3 つの視点から確認できます。

### 1. Overview — 2 ランの並列比較

同じ `scrubber_degradation` 異常に対し、**異なる LLM エージェント**（例: `qwen2.5` vs `gemma4:e4b`）がどう違う軌道を描くかを step 単位で比較します。CO2 ppm・電力マージン・EPS 支援・スクラバー効率のプロットが横並びで並び、モデル間のトレードオフ（CO2 抑制 vs 電力消費など）が一目でわかります。

<p align="center">
  <img src="../docs/images/dashboard-overview-compare.png" alt="ECLSS Resilience Dashboard — Overview で 2 つの LLM run を step 49 で横並び比較" width="900"/>
</p>

### 2. 設計提案 — トポロジの Before / After

ラン終了後、代表エージェントが **恒久設計変更** を提案します。左はバイパス弁（`bypass_valve`）の追加、右は非常電源（`emergency_power_source`）の追加といった案で、赤破線が提案エッジ、ノード表の `proposed` 列が新規部品を示します。

<p align="center">
  <img src="../docs/images/dashboard-topology-proposals.png" alt="設計提案 — バイパス弁と非常電源の 2 つのトポロジ変更案" width="900"/>
</p>

### 3. Step replay — ステップ単位の詳細再生

1 run を step ごとに追い、**タイムライン**（回復コマンドの適用）、**エージェント発言**、**reasoning**（状況判断の根拠）、**テレメトリプロット**（現 step の縦線マーカー）を同期表示します。下図は step 17 で `request_eps_boost` が適用された瞬間の例です。

<p align="center">
  <img src="../docs/images/dashboard-step-replay.png" alt="Step replay — scrubber_degradation_llm の step 17、EPS ブースト適用とエージェント reasoning" width="900"/>
</p>

---

## なぜこのシミュレーションか

宇宙ステーションでは、CO2 除去（スクラバー）や電力マージンの悪化が連鎖すると、乗員の安全に直結します。現実では：

1. テレメトリで異常を検知する  
2. 運用チームが状況を共有し、一時的な回復操作を打つ  
3. 恒久対策としてハードウェア／配管／電源の設計変更を検討する  

この **レジリエンス・ループ** を、再現可能な実験環境で回したいのが本プロジェクトの出発点です。

参照シナリオ [`scrubber_degradation`](docs/scenario-scrubber-degradation.md) では、step 20 からスクラバー効率が落ち、CO2 と電力マージンが悪化します。エージェントはランタイム中に回復コマンドを出し、**ラン終了後**にトポロジ変更案（バイパス弁の追加、非常電源の追加など）を `design_proposals.json` に残します。

---

## なぜ LLM か（ルールベースとの違い）

| | `labeled_rule_base` | `llm` |
| --- | --- | --- |
| 判断の源泉 | `agents.yaml` の `policy` 閾値（例: 回復開始 CO2 1000 ppm） | Persona + テレメトリ + チーム発言（**policy は読まない**） |
| 議論 | ルールが決めた定型メッセージ | 同種エンジニア N 体が 1 ラウンド deliberation |
| 行動 | 代表 `engineer_{(step-1)%N}` が閾値に応じてコマンド | 代表が LLM 出力の `commands` を実行 |
| 再現性 | 高い（回帰テスト向き） | モデル・温度に依存（比較実験向き） |
| 研究価値 | ベースライン・正解比較 | 「閾値の外」での状況判断、発言の多様性、設計提案の差 |

ルールベースは **「正しい挙動の足場」** です。LLM モードは、固定閾値では表現しきれない **状況理解・チーム合意・回復タイミングの違い** を観察するための実験モードです。LLM 設計で重要だった点は次のとおりです（詳細は [homogeneous agent team plan](memo/homogeneous_agent_team_plan.md)）。

- **Persona とシナリオの分離** — 閾値や数値はプロンプトの `### Telemetry` / `### World state` にだけ載せる  
- **同種 N 体 + 代表 action** — 役割の硬直を避け、step ごとに発言者と実行者をローテーション  
- **ランタイム中はトポロジ変更しない** — シミュレーションと設計提案を分離し、One Piece provenance と整合  
- **policy を LLM から隔離** — ルールの答えをプロンプトに混ぜず、比較実験を可能にする  

---

## シミュレーション世界（用語）

| 略称 | 英語名 | 説明 |
| --- | --- | --- |
| **ECLSS** | Environmental Control and Life Support System | **生命維持装置**。CO2 スクラバー・送気配管・居住空間をグラフで表現 |
| **EPS** | Electrical Power System | 発電・蓄電・配電。SARJ/BCDU モックを通じ ECLSS へ電力支援 |
| **SARJ** | Solar Alpha Rotary Joint | 太陽電池アレイ発電（`MockSarj`） |
| **BCDU** | Battery Charge/Discharge Unit | 蓄電放電。電力 critical 時に `request_eps_boost` で支援 |
| **MBSU** | Main Bus Switching Unit | 実 EPS の主バス（本 MVP モック未個別実装） |
| **DDCU** | Direct Current-to-Direct Current Converter Unit | 実 EPS の DC-DC 変換（本 MVP モック未個別実装） |
| **ノード** | — | プラント構成要素（`cabin`, `manifold`, `scrubber`, `power_bus` など） |
| **エッジ** | — | ノード間の `flow`（空気）または `power`（電力） |
| **テレメトリ** | — | 各 step の CO2 ppm、スクラバー効率、電力マージン、EPS 支援ワットなど |
| **回復コマンド** | — | 一時操作（ファン加速、負荷削減、EPS ブースト、バイパス有効化） |
| **設計提案** | — | ラン終了後の恒久変更（ノード／エッジ追加、パラメータ変更） |

**ヘルス閾値**（`health_metrics.jsonl`）: CO2 safe < 800 / warning < 1200 / critical ≥ 1200 ppm；電力マージン safe > 0 / warning > −150 / critical ≤ −150 W。詳細は [architecture.md](docs/architecture.md)。

### デフォルトトポロジ

```
  [cabin] --flow--> [manifold] --flow--> [scrubber] --flow--> [cabin]
                                              ^
                                              | power
                                         [power_bus]
```

異常 `scrubber_degradation` によりスクラバー効率が段階的に低下し、CO2 産生倍率と電力マージンの縮小が同時に進行します。仕様・フェーズ表は [scenario-scrubber-degradation.md](docs/scenario-scrubber-degradation.md) を参照してください。

### エージェントチーム（同種エンジニア N 体）

- デフォルト 4 体: `engineer_1` … `engineer_4`（`agents.yaml` の `team.count` で変更可）  
- 各 step: 全員が状況を議論（llm）またはルールが定型診断（labeled_rule_base）  
- **代表** `engineer_{(step-1) % N}` がその step の回復コマンドを発行  
- **事後設計**は最終 step の代表が `design_proposals.json` を出力（[設計提案のスクショ](#2-設計提案--トポロジの-before--after) 参照）

---

## このリポジトリと SSOS / One Piece の位置づけ

```text
[ 本リポジトリ MVP ]
  MockEclssSimulator + EpsStack (Python)
       ↑ SimulatorProtocol
  ScrubberDegradationTeam (agents)
       ↓ JSONL ログ
  Streamlit dashboard / pytest

[ 開発途中 ]
  SSOS adapter     … 実 SSOS トピックへのブリッジ（契約テストのみスタブ）
  One Piece 本番 UI … provenance JSON のみ実装済み、Web UI はスコープ外
```

| 領域 | 状態 | 参照 |
| --- | --- | --- |
| SSOS モックシミュレーション | **利用可能** | [architecture.md](docs/architecture.md) |
| One Piece provenance エクスポート | **利用可能** | [one-piece-integration.md](docs/one-piece-integration.md) |
| SSOS 実機アダプタ | 計画・スタブ | [development-plan.md](docs/development-plan.md) |
| One Piece Web / SSOT UI | 未接続 | [one-piece-integration.md](docs/one-piece-integration.md) |

開発途中のタスク・ロードマップ・研究メモは [docs/development-plan.md](docs/development-plan.md) に集約しています。

---

## ドキュメント

| ドキュメント | 対象読者 | 内容 |
| --- | --- | --- |
| [docs/architecture.md](docs/architecture.md) | コントリビュータ | レイヤ構成、実行フロー、エージェントモード、ダッシュボード |
| [docs/scenario-scrubber-degradation.md](docs/scenario-scrubber-degradation.md) | デモ・分析 | シナリオ背景、設定、出力の読み方、テスト |
| [docs/api-contracts.md](docs/api-contracts.md) | インテグレータ | `SimulatorProtocol`、JSONL、`design_proposals.json` |
| [docs/one-piece-integration.md](docs/one-piece-integration.md) | 設計追跡 | provenance、One Piece 連携の現状と予定 |
| [docs/development-plan.md](docs/development-plan.md) | 開発者 | 未完了機能、ロードマップ、`ja/memo/` 索引 |

---

## 必要条件

- **Python 3.9+**
- **Git**
- **Ollama**（`agents.mode: llm` を使う場合のみ）

---

## インストール（ゼロから）

### 1. リポジトリを取得

```bash
git clone <repository-url>
cd engineering_agents
```

### 2. Python 仮想環境とパッケージ

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[dev]"
```

`pip install -e ".[dev]"` により `src/` 配下の `scenario`, `environment`, `core` などが import 可能になります。

### 3. 動作確認（テスト）

```bash
pytest
# または
python src/scripts/run_tests.py
```

### 4. Ollama（LLM モード用）

[https://ollama.com](https://ollama.com) から Ollama をインストールし、デーモンを起動します。

```bash
# 例: agents.yaml で指定しているモデルを pull
ollama pull gemma4:e4b

# 別モデルで試す場合は agents.yaml の llm.model を変更するか、
# 実行後に run_id を変えて比較してください
ollama list
```

デフォルトの LLM 設定は [`src/scenario/scrubber_degradation/agents.yaml`](../../src/scenario/scrubber_degradation/agents.yaml)（`base_url: http://localhost:11434`）です。Ollama が起動していないと `llm` モードは失敗します。

---

## 実行方法

### エージェントなし（ベースライン）

```bash
python src/scripts/run_mock_eclss.py
```

または:

```bash
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'none'}}))"
```

### ルールベースチーム（`labeled_rule_base`）

```bash
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}}))"
```

出力先: `src/experiments/results/scrubber_degradation_labeled_rule_base/`

### LLM チーム（`llm`・Ollama 必須）

```bash
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}}))"
```

出力先: `src/experiments/results/scrubber_degradation_llm/`（`scenario.yaml` の `run_id_llm`）

別モデルで別 run 名にしたい場合は、実行前に `agents.yaml` の `llm.model` を変更するか、`output.run_id_llm` をオーバーライドしてください。

### 主な出力ファイル

| ファイル | 説明 |
| --- | --- |
| `telemetry.jsonl` | CO2、効率、電力マージン、EPS 支援など |
| `messages.jsonl` | エージェント発言・reasoning |
| `events.jsonl` | 異常注入、回復コマンド、設計変更イベント |
| `design_state.jsonl` | 各 step 開始時点のトポロジ（エージェント行動前） |
| `design_proposals.json` | ラン終了後の恒久設計案 |
| `summary.json` | 実行サマリ（`agents_mode`, 最終 CO2 など） |

スキーマ詳細: [docs/api-contracts.md](docs/api-contracts.md)

---

## ダッシュボード

```bash
source .venv/bin/activate
python -m streamlit run src/tools/dashboard/app.py
```

ブラウザで `http://localhost:8501` を開きます。表示例は冒頭の [一目でわかる（ダッシュボード）](#一目でわかるダッシュボード) を参照してください。

- **Overview** — 単一 run または 2 run 比較（テレメトリ・トポロジ・step 詳細）  
- **Step replay** — タイムライン・発言・思考を step ごとに再生  
- サイドバーで run 選択、`Compare with another run` で LLM 同士などを比較可能  

実行結果の保存先: `src/experiments/results/<run_id>/`

---

## リポジトリ構成

| パス | 用途 |
| --- | --- |
| `src/core/agents/` | Persona、Team、メモリ、LLM クライアント |
| `src/environment/` | `SimulatorProtocol`、ECLSS/EPS モック、SSOS adapter スタブ |
| `src/scenario/` | シナリオ YAML、runner、`scrubber_degradation` チーム |
| `src/experiments/results/` | 実行結果（gitignore 推奨） |
| `src/tools/dashboard/` | Streamlit UI |
| `src/integrations/one_piece/` | provenance レコード生成 |
| `ja/docs/` | 設計・API・シナリオドキュメント（開発プラン含む） |
| `ja/memo/` | 実装プロセス記録・バックログ（[development-plan.md](docs/development-plan.md) から参照） |
| `en/docs/` | English documentation |
| `en/memo/` | English research memos |

依存方向: `tools → scenario → environment → core`

---

## ライセンス

[Apache License 2.0](LICENSE.txt) — Copyright 2026 Hiroto Tamura

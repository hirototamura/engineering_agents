# ECLSS Resilience Loop — ディレクトリ構成 & 1週間 MVP 計画

> 設計プロセス記録。Cursor プラン `ECLSS Agent Directory MVP` から export（2026-05-30）。  
> **2026-05-30 更新**: Day 1–2 完了後の振り返りに基づきロードマップを修正。  
> **2026-05-30 更新**: Day 4 ロール設計方針・研究バックログ（[backlog.md](backlog.md)）を追記。  
> **2026-05-31 更新**: Day 5 を **LLM統合優先（Day5A: labeled_shadow）** に再編。  
> **2026-05-31 更新**: Day5B 完了を反映し、Day6 以降の実装順を再計画。  
> **2026-06-02 更新**: ECLSS 単独では power margin 回復手段が不足するため、次フェーズ最優先を **EPS モック統合** に変更。  
> **2026-06-02 更新**: EPS の Day 区切り詳細は [eps_implementation_plan.md](eps_implementation_plan.md) を参照。  
> **2026-06-02 更新**: **EPS-1〜4 完了**（`feature/eps-mock-foundation`）。次は Day 8 CLI。  
> **2026-06-02 更新**: `labeled_shadow` モードを廃止（`labeled` / `labeled_llm_guarded` の2系統に整理）。

## ゴール

**本質**: 精緻な物理モデルより「構造化されたエージェント関係」と「シミュレーターとの確実な API 契約」。

**現在のフェーズ（Phase 1）**: ECLSS 向け `src/` レイヤー上で、**scrubber_degradation ベースラインシナリオ**を常に実行可能な状態で維持しながら、エージェント・UI・設計変更トラックを足していく。

### 前提（ユーザー確認済み）

- **リポジトリ方針**: 既存 bar sim は `src/materials/` に退避。`src/` 配下に `core`, `environment`, `experiments`, `scenario`, `scripts`, `tools`。`src` と同レベルに `docs`, `memo`, `tests`。
- **SSOS 連携**: Mock アダプタ先行（ROS2 topic / command API 互換）。後から real SSOS に差し替え。
- **開発ブランチ**: `feature/eclss-mvp`（ECLSS+agents PR 済み）／EPS 作業は `feature/eps-mock-foundation`
- **実行前提**: `pip install -e ".[dev]"` で `scenario` / `integrations` を import 可能にする（`integrations` は `src/integrations/`）

---

## Day 1–2 振り返り（完了）

| 項目 | 状態 | メモ |
| --- | --- | --- |
| `src/` レイヤー分離 + materials 退避 | ✅ | Day 1 |
| `core/`（sim loop, LLM, event_log） | ✅ | Day 1 で前倒し完了（旧 Day 3 項目） |
| `SimulatorProtocol` + Mock ECLSS | ✅ | Day 2 |
| `telemetry.jsonl` / `health_metrics.jsonl` | ✅ | Day 2 |
| `docs/api-contracts.md` | ✅ | Day 2 |
| pytest 8件 | ✅ | |

### Day 2 で判明したギャップ（Day 3 で解消）

1. **scrubber_degradation がシナリオとして未整備** — ロジックが `scripts/run_mock_eclss.py` にハードコードされていた。
2. **デモ物語が未成立** — 異常前から scrub が production を上回り CO2 が単調減少。危険域（>1000 ppm）に到達しない。
3. **ベースライン回帰テスト不足** — シナリオ名付きガードテストがなかった。

**方針**: アーキテクチャは維持。Day 3 以降の優先順位のみ修正（全面プラン見直しは不要）。

---

## 修正版 1週間 MVP ロードマップ

| Day | 旧プラン | **修正後（採用）** | 状態 |
| --- | --- | --- | --- |
| **1** | ディレクトリ移行 + pyproject | 同左 | ✅ 完了 |
| **2** | Mock ECLSS + Protocol + telemetry | 同左 | ✅ 完了 |
| **3** | core 抽出 + runner 骨格 | **scrubber_degradation 正式化 + runner + 物理調整 + baseline 回帰テスト** | ✅ 完了 |
| **4** | 4 ロール LLM エージェント | **scrubber_degradation 専用・ルールベース 4 ロール** + 回復ループ | ✅ 完了 |
| **5** | One Piece JSON provenance | **Day5A: LLM shadow 統合**（`agents.mode: labeled_shadow`）→ **Day5B: One Piece provenance** | ✅ Day5B 完了 |
| **6** | Streamlit ダッシュボード | 左チャット + 右 CO2 グラフ（JSONL tail） + provenance step同期表示 | ✅ 完了 |
| **7** | E2E + CLI | `tools.cli run --scenario scrubber_degradation` 完走 | 未着手 |

### Day 1–5 振り返り（2026-05-31）

| 観点 | 状態 | 補足 |
| --- | --- | --- |
| ベースライン安定性 | ✅ | `agents.mode: none` を維持。`anomaly_injected` 重複記録も修正済み。 |
| エージェント統合 | ✅ | `labeled`（rule）と `labeled_llm_guarded`（LLM + guard + fallback）。 |
| shadow 品質（廃止） | — | Day5A の `labeled_shadow` は 2026-06-02 に削除。履歴は Day 5A メモ参照。 |
| One Piece provenance | ✅ | `provenance.jsonl` 自動生成、`summary.provenance_*` 追記。 |
| 未完了 | ⏳ | CLI / E2E / SSOS adapter 契約テスト（Day 8–10）。EPS は [eps_implementation_plan.md](eps_implementation_plan.md) 参照。 |

### Day 6+ 実装順（更新）

| フェーズ | 優先タスク | 完了条件 |
| --- | --- | --- |
| **Day 6** | `tools/dashboard/app.py` 実装（telemetry/health/messages/provenance の同時可視化） | ✅ step同期で CO2推移・役割メッセージ・設計変更履歴を1画面確認 |
| **Next-1 (Week-2入口)** | SSOS EPS モック統合 — [EPS-1〜4](eps_implementation_plan.md#day-区切りロードマップ) | ✅ EPS-1〜4 完了 |
| **Next-2** | CLI 統合 — [Day 8](eps_implementation_plan.md#day-8-cli1日) | 1コマンドで baseline/labeled/labeled_llm_guarded 実行 + 出力先表示 |
| **Next-3** | One Piece連携拡張 — [Day 9](eps_implementation_plan.md#day-910-拡張) | run横断で provenance 集計可能、one-piece 側への受け渡し仕様確定 |
| **Next-4** | SSOS adapter 前倒し準備 — [Day 10](eps_implementation_plan.md#day-910-拡張) | `SsosAdapter` に必要な I/O 契約とテストスタブを確定 |

### Week-2 振り返り — EPS モック（2026-06-02、`feature/eps-mock-foundation`）

| 項目 | 状態 | 補足 |
| --- | --- | --- |
| EPS-1 `request_eps_boost` | ✅ | Operator ルール回復経路 |
| EPS-2 SARJ + BCDU | ✅ | 薄モック + `test_mock_eps.py` |
| EPS-3 `StationSimulator` | ✅ | `summary.simulator: mock_station`、ECLSS 単体は boost 拒否 |
| EPS-4 可観測性 | ✅ | `eps_telemetry.jsonl`、recovery provenance、dashboard SARJ/BCDU |
| パッケージング | ✅ | `integrations` を `src/integrations/` へ移動し `pip install -e` で一貫 import |

**次**: Day 8 CLI → Day 9 provenance index → Day 10 SSOS adapter 契約テスト。

**Week-1 でやらないこと**（据え置き）:

- Real SSOS / ROS2 ランタイム接続
- One Piece Web UI 統合
- LLM 必須化（deterministic baseline を主軸）
- batch sweep / 動画生成

---

## デモシナリオ: `scrubber_degradation`（ベースライン）

**最重要**: Week-1 を通じて **常に LLM なしで完走**できるベースライン。改変後は `pytest tests/scenario/test_scrubber_baseline.py` で確認。

- **初期状態**: CO2 ≈ 800 ppm、scrubber efficiency 0.95
- **Step 20**: 複合アノマリー — 効率低下 + 電力圧迫 + CO2 产生増
- **物語**: Step 1–19 均衡付近 → Step 20 以降 CO2 **>1000 ppm** → Day 4 以降回復・設計変更で安全域へ
- **ベースライン成功条件**: 50 step 完走、step 20 anomaly、peak CO2 > 1000、ログ出力

### Day 4 — エージェントロール設計方針

**原則: 汎用化しすぎない。シナリオに即した特定ロールから始める。**

| やること | やらないこと（Week-1） |
| --- | --- |
| `scrubber_degradation/agents.yaml` に **このシナリオ専用**の 4 ロール定義 | 任意シナリオ向け汎用ロールフレームワーク |
| Monitor / Diagnostician / Operator / DesignEngineer を **ルールベース**で実装 | LLM 必須化 |
| `agents.mode: none \| labeled`（baseline 維持） | `agents.mode: base`（創発ロール実験） |

4 ロールは「異常を溶かす」ための **暫定ラベル**である。人間の分業をそのまま写したものなので、ラベルを与えない場合に Base Role エージェントが状況に即した役割を創発するかは別問題 — **[backlog.md BL-001](backlog.md)** でトラックする。

**Day 4 完了条件（labeled モード）**

- `messages.jsonl` に 4 ロール由来の構造化メッセージ
- Operator 回復コマンド → CO2 安全域へ向かう
- DesignEngineer 設計変更（bypass）が `design_state` に反映
- `test_scrubber_baseline.py` は `agents.mode: none` のまま green

### Day 5A — labeled_shadow 品質メモ（2026-05-31、モードは 2026-06-02 廃止）

- `qwen3.5:2b` + prompt 制約緩和（JSON object only, multi-line 許可）で `parse_status` が改善
- 20 step 試験（80件）で **ok=79 / fallback=1（fallback率 1.25%）**
- fallback はすべて `no balanced JSON object found`（JSON抽出失敗）由来
- 現状 fallback は制御に影響しない（shadow ログのみ）。Day5B 以降は provenance に `parse_status` を保存して監査可能性を維持する

### Day 5B — One Piece provenance 実装メモ（2026-05-31）

- `integrations/one_piece/client.py` を追加し、run終了時に `provenance.jsonl` を自動生成
- `events.jsonl`（design_change）+ `messages.jsonl` + `design_state.jsonl` を突合して記録
- `summary.json` に `provenance_path` / `provenance_record_count` を追加
- baseline では `provenance_record_count=0`、labeled / labeled_llm_guarded では設計変更ぶん記録

### Next — EPS優先方針（2026-06-02）

詳細ロードマップ: **[eps_implementation_plan.md](eps_implementation_plan.md)**（EPS-1 基盤着地 → EPS-2 SARJ+BCDU → EPS-3 facade → EPS-4 可観測性 → Day 8–10）。

- 課題: ECLSS 単独の回復コマンドでは power margin の根本回復が難しく、critical 化が不可避になりやすい
- 方針: One Piece/CLI 拡張より先に、[space_station_eps](https://github.com/space-station-os/space_station_os/tree/main/space_station_eps) に着想を得た EPS モックを導入（薄いモック、SARJ 含む）
- 実装軸:
  - `request_eps_boost` コマンドを回復経路へ追加（EPS-1）
  - SARJ → BCDU → ECLSS 連動（EPS-2〜3）
  - provenance / dashboard で「ルール vs LLM の電力回復差」を可視化（EPS-4）

---

## バックログ（MVP 外・研究）

詳細は [memo/backlog.md](backlog.md)。

| ID | テーマ | 概要 |
| --- | --- | --- |
| **BL-001** | ロールラベル vs 創発 | Labeled 4 ロール vs Base Role（ラベルなし）の比較実験 |
| BL-002 | （予約） | — |

---

## テスト方針

| テスト | 目的 |
| --- | --- |
| `tests/environment/test_mock_eclss.py` | Mock 単体 |
| **`tests/scenario/test_scrubber_baseline.py`** | **ベースライン完走 + 物語 assert（毎コミット必須）** |

### ベースライン assert（Day 3）

1. `run_scenario("scrubber_degradation")` 完走
2. `telemetry.jsonl` N 行 + `health_metrics.jsonl` / `events.jsonl` / `summary.json` 存在
3. step 20 以降 `anomaly_flags` に `scrubber_degradation`
4. `peak_co2_ppm > 1000`

---

## 成功判定（MVP Done）

1. `python -m tools.cli run --scenario scrubber_degradation` 完走 — **未着手（Day 8）**；暫定は `run_scenario` / `run_mock_eclss.py`
2. ログ + `summary.json` 出力 — **7 ストリーム**（`eps_telemetry.jsonl` 含む）+ `provenance.jsonl` ✅
3. Streamlit step 同期 UI（EPS チャート含む）✅
4. 設計変更 + EPS recovery が `provenance.jsonl` に記録 ✅
5. **`pytest tests/scenario/test_scrubber_baseline.py` が常に green** ✅

---

## 実装タスク一覧

- [x] src/ 骨格作成
- [x] 既存 bar sim を materials へ移行
- [x] SimulatorProtocol + JSONL スキーマ
- [x] mock_eclss.py + ROS2-like topics
- [x] core 一般化移植
- [x] scrubber_degradation scenario.yaml + runner + baseline 回帰テスト
- [x] Mock 物理パラメータ調整（CO2 危険域到達）
- [x] scrubber_degradation 専用・ルールベース 4 ロール（agents.yaml、`mode: labeled_rule_base`）
- [ ] BL-001 創発ロール実験（`mode: base`）— バックログ、Week-1 外
- [x] Day5A: LLM shadow 統合（`agents.mode: labeled_shadow`、`decision_source`/`parse_status` ログ）
- [x] Day5B: `src/integrations/one_piece/` provenance（`provenance.jsonl`, `summary.provenance_*`）
- [x] tools/dashboard/app.py（run選択 / step slider / telemetry+messages+events+provenance 可視化）
- [x] labeled_llm_guarded 追加（Monitor/Diagnostician/Operator は LLM採用、DesignEngineer は guard付きLLM採用）
- [x] EPS-1: `request_eps_boost` 回復経路（インライン；EPS-3 で facade 化）— [eps_implementation_plan.md](eps_implementation_plan.md)
- [x] EPS-2: `MockSarj` / `MockBcdu` / `EpsStack` + `test_mock_eps.py`
- [x] EPS-3: `StationSimulator` + runner `mock_station`
- [x] EPS-4: `eps_telemetry.jsonl` + recovery provenance + dashboard EPS パネル
- [ ] tools/cli + scrubber_demo.yaml E2E（Day 8）

---

## 参考

- **EPS Day 区切り実装プラン**: [eps_implementation_plan.md](eps_implementation_plan.md)
- ドキュメント索引: [README.md](../../README.md#ドキュメント)、開発プラン: [docs/development-plan.md](../../development-plan.md)
- API 契約: [docs/api-contracts.md](../../api-contracts.md)
- アーキテクチャ: [docs/architecture.md](../../architecture.md)
- シナリオ: [docs/scenario-scrubber-degradation.md](../../scenario-scrubber-degradation.md)
- One Piece: [docs/one-piece-integration.md](../../one-piece-integration.md)

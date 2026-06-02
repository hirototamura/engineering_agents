# ECLSS Resilience Loop — ディレクトリ構成 & 1週間 MVP 計画

> 設計プロセス記録。Cursor プラン `ECLSS Agent Directory MVP` から export（2026-05-30）。  
> **2026-05-30 更新**: Day 1–2 完了後の振り返りに基づきロードマップを修正。  
> **2026-05-30 更新**: Day 4 ロール設計方針・研究バックログ（[backlog.md](backlog.md)）を追記。  
> **2026-05-31 更新**: Day 5 を **LLM統合優先（Day5A: labeled_shadow）** に再編。  
> **2026-05-31 更新**: Day5B 完了を反映し、Day6 以降の実装順を再計画。

## ゴール

**本質**: 精緻な物理モデルより「構造化されたエージェント関係」と「シミュレーターとの確実な API 契約」。

**現在のフェーズ（Phase 1）**: ECLSS 向け `src/` レイヤー上で、**scrubber_degradation ベースラインシナリオ**を常に実行可能な状態で維持しながら、エージェント・UI・設計変更トラックを足していく。

### 前提（ユーザー確認済み）

- **リポジトリ方針**: 既存 bar sim は `src/materials/` に退避。`src/` 配下に `core`, `environment`, `experiments`, `scenario`, `scripts`, `tools`。`src` と同レベルに `docs`, `memo`, `tests`。
- **SSOS 連携**: Mock アダプタ先行（ROS2 topic / command API 互換）。後から real SSOS に差し替え。
- **開発ブランチ**: `feature/eclss-mvp`

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
| **6** | Streamlit ダッシュボード | 左チャット + 右 CO2 グラフ（JSONL tail） + provenance step同期表示 | ✅ 実装完了（検証中） |
| **7** | E2E + CLI | `tools.cli run --scenario scrubber_degradation` 完走 | 未着手 |

### Day 1–5 振り返り（2026-05-31）

| 観点 | 状態 | 補足 |
| --- | --- | --- |
| ベースライン安定性 | ✅ | `agents.mode: none` を維持。`anomaly_injected` 重複記録も修正済み。 |
| エージェント統合 | ✅ | `labeled`（rule）と `labeled_shadow`（rule + LLM観測）を分離。 |
| shadow 品質 | ✅ 改善 | `qwen3.5:2b` で 20 step / 80件中 `ok=79`, `fallback=1`（1.25%）。 |
| One Piece provenance | ✅ | `provenance.jsonl` 自動生成、`summary.provenance_*` 追記。 |
| 未完了 | ⏳ | dashboard / CLI / E2E / SSOS実接続準備。 |

### Day 6+ 実装順（更新）

| フェーズ | 優先タスク | 完了条件 |
| --- | --- | --- |
| **Day 6** | `tools/dashboard/app.py` 実装（telemetry/health/messages/provenance の同時可視化） | ✅ step同期で CO2推移・役割メッセージ・設計変更履歴を1画面確認 |
| **Day 7** | CLI 統合（`tools.cli run --scenario ... --agents-mode ...`）+ E2E整理 | 1コマンドで baseline/labeled/labeled_shadow/labeled_llm_guarded 実行 + 出力先表示 |
| **Day 8 (Week-2入口)** | One Piece連携拡張（provenance summary index, optional connector hook） | run横断で provenance 集計可能、one-piece 側への受け渡し仕様確定 |
| **Day 9 (Week-2入口)** | SSOS adapter 前倒し準備（topic mapテスト、mockとの差分明示） | `SsosAdapter` に必要な I/O 契約とテストスタブを確定 |

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

### Day 5A — labeled_shadow 品質メモ（2026-05-31）

- `qwen3.5:2b` + prompt 制約緩和（JSON object only, multi-line 許可）で `parse_status` が改善
- 20 step 試験（80件）で **ok=79 / fallback=1（fallback率 1.25%）**
- fallback はすべて `no balanced JSON object found`（JSON抽出失敗）由来
- 現状 fallback は制御に影響しない（shadow ログのみ）。Day5B 以降は provenance に `parse_status` を保存して監査可能性を維持する

### Day 5B — One Piece provenance 実装メモ（2026-05-31）

- `integrations/one_piece/client.py` を追加し、run終了時に `provenance.jsonl` を自動生成
- `events.jsonl`（design_change）+ `messages.jsonl` + `design_state.jsonl` を突合して記録
- `summary.json` に `provenance_path` / `provenance_record_count` を追加
- baseline では `provenance_record_count=0`、labeled/labeled_shadow では設計変更ぶん記録

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

1. `python -m tools.cli run --scenario scrubber_degradation` 完走
2. 6 種ログ + `summary.json` 出力
3. Streamlit step 同期 UI
4. 設計変更が `design_state.jsonl` + One Piece provenance に記録
5. **`pytest tests/scenario/test_scrubber_baseline.py` が常に green**

---

## 実装タスク一覧

- [x] src/ 骨格作成
- [x] 既存 bar sim を materials へ移行
- [x] SimulatorProtocol + JSONL スキーマ
- [x] mock_eclss.py + ROS2-like topics
- [x] core 一般化移植
- [x] scrubber_degradation scenario.yaml + runner + baseline 回帰テスト
- [x] Mock 物理パラメータ調整（CO2 危険域到達）
- [x] scrubber_degradation 専用・ルールベース 4 ロール（agents.yaml、`mode: labeled`）
- [ ] BL-001 創発ロール実験（`mode: base`）— バックログ、Week-1 外
- [x] Day5A: LLM shadow 統合（`agents.mode: labeled_shadow`、`decision_source`/`parse_status` ログ）
- [x] Day5B: integrations/one_piece/ provenance（`provenance.jsonl`, `summary.provenance_*`）
- [x] tools/dashboard/app.py（run選択 / step slider / telemetry+messages+events+provenance 可視化）
- [x] labeled_llm_guarded 追加（Monitor/Diagnostician/Operator は LLM採用、DesignEngineer は guard付きLLM採用）
- [ ] tools/cli + scrubber_demo.yaml E2E

---

## 参考

- ドキュメント索引: [docs/README.md](../docs/README.md)
- API 契約: [docs/api-contracts.md](../docs/api-contracts.md)
- アーキテクチャ: [docs/architecture.md](../docs/architecture.md)
- シナリオ: [docs/scenario-scrubber-degradation.md](../docs/scenario-scrubber-degradation.md)
- One Piece: [docs/one-piece-integration.md](../docs/one-piece-integration.md)

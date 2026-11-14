# 開発履歴

過去の開発計画・進捗記録です。CLI v3 は現在利用可能です。このページのテスト件数・予定日は当時の記録であり、現行の状態は[親ページ](../../../../ja/users/scenarios/ssos_eclss_loop/index.md)と[評価](../../../../ja/developers/scenarios/ssos_eclss_loop/evaluation.md)を参照してください。

### ssos_eclss_loop（SSOS 実 ECLSS）— Phase 0–7 完了


| Phase | 内容                                                         | 状態                                                                                  |
| ----- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| 0     | ランタイム `DesignChange` 削除                                    | ✅                                                                                   |
| 1a–1b | ARS/OGS smoke、`EclssBackend`、`Ros2EclssBridge`             | ✅                                                                                   |
| 2     | WRS ブリッジ                                                   | ✅                                                                                   |
| 4     | `ssos_eclss_loop` + `SsosEclssLoopTeam`                    | ✅                                                                                   |
| 5     | `design_proposals.json`（`ssos_graph`）+ `--apply-proposals` | ✅                                                                                   |
| 6     | LLM エージェント + Docker `ea-loop`（ros2 / Ollama デフォルト）         | ✅                                                                                   |
| 7     | クライアント `graph_rewire`、`Team` ABC、ダッシュボード ssos ビュー          | ✅                                                                                   |
| 8     | ROS launch remap + ゲートウェイ                                  | 📋 [backlog BL-003](backlog.md#bl-003) |


**テスト**: `pytest --ignore=tests/e2e` — **205 passed**, 4 skipped（ROS2 live / コンテナ外は skip）。

**コンテナ回帰**: `./scripts/run_ssos_regression.sh`（Tier 1 pytest。Tier 2 は `SSOS_E2E=1`）。CI: `.github/workflows/ssos-e2e.yml`。

**時間モデル（現状）**: `mock` は 1 EA step = 1 物理 tick。`ros2` は SSOS 実時間のスナップショット駆動（step 同期なし）。run 間リセットは headless 再起動。step 同期の方針検討は [BL-007](backlog.md#bl-007)。

**コンテナ実行（目標）**: `scripts/ssos/mac/ssos-run-detached.sh`（src + results + ヘルパーマウント）→ ホスト `ea run ssos_eclss_loop` のみ。headless 再起動は CLI 内部 bash が担当。

---



## 進行中


| 項目                           | 説明                                                                                          | 参照                                                           |
| ---------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **CLI v3 — SSOS ホスト 1 コマンド** | ボリュームマウント + `ea run ssos_eclss_loop`（内部 bash）、`duration_wall_s`、rclpy shutdown、`ea results` | [cli.md](../../../../ja/users/reference/cli.md), [memo/cli_v3_plan.md](cli_v3_plan.md) |
| LLM 比較実験                     | モデル・温度・run_id を変えた軌道比較（ダッシュボード compare）                                                     | [architecture.md](../../../../ja/developers/architecture.md)                           |
| ドキュメント整備                     | `docs/ja/` / `docs/en/` をコード・memo と同期                                                          | [MAINTENANCE.md](../../../../ja/developers/development/documentation.md)                                                          |


**CLI v3 スコープ外**（バックログ）: ros2 プラント初期状態とシナリオ kg 閾値の検証、Streamlit SSOS リッチ表示 → [BL-006](backlog.md#bl-006)

**接合の次段階（検討）**: EA step と SSOS 物理時間の同期 — Mock 拡充 vs upstream sim clock → [BL-007](backlog.md#bl-007)（CLI v3 / Phase 8 とは別トラック）

---



## 次の実装（優先順）

1. **provenance 拡張** — scrubber / ssos の `design_proposals.json` を One Piece レコードへエクスポート
2. **provenance インデックス** — 複数 run 横断の `provenance_index.json`
3. **Phase 8 — ROS launch remap** — `graph_rewire` の launch 適用（BL-003）
4. **ECLSS + EPS 単一 ros2 シナリオ** — 電力危機と SSOS ECLSS を同一 run（BL-004）
5. **EPS 3b/3c** — BCDU discharge 直接呼び出し、`/bcdu/operation` Action（BL-005）

---



## その後（スコープ外に近い）


| 項目                         | 状態                       | 参照                                                        |
| -------------------------- | ------------------------ | --------------------------------------------------------- |
| One Piece Web / SSOT UI    | 未接続（JSON provenance のみ）  | [one-piece-integration.md](../../../../ja/developers/records-integrations.md)      |
| `agents.mode: base`        | 未実装（創発ロール）               | [backlog.md](../../../../ja/developers/index.md) BL-001                      |
| 進化ペルソナ研究                   | バックログ                    | BL-002                                                    |
| WRS in `SsosEclssLoopTeam` | **実装済み** — labeled/llm が `water_recovery` を発行。LoopMock は例外 | `ssos_eclss_loop_team.py` |
| upstream CO₂ スクラバ          | SSOS 拡張待ち                | BL-004                                                    |
| MkDocs CI deploy           | `docs/ssos-mkdocs`       | BL-004                                                    |
| SSOS ↔ EA step 同期          | 検討中（Mock 拡充 vs upstream） | [BL-007](backlog.md#bl-007) |


---



## ロードマップ（時系列）

```text
[完了 — scrubber MVP]
  Day 1–6   レイヤ分離、scrubber_degradation、ダッシュボード
  EPS-1–4   SARJ/BCDU モック、StationSimulator、eps_telemetry
  同種 N 体 LLM チーム

[完了 — SSOS 接合 Phase 0–7]
  1a–2     EclssBackend、ARS/OGS/WRS、Ros2EclssBridge
  3        Ros2EpsBridge（scrubber 電力）
  4–6      ssos_eclss_loop、design_proposals、LLM、ea-loop
  7        client graph_rewire、Team ABC、ssos ダッシュボード
  Day 8    CLI（`ea run`、RunSpec、クラスタ向け job runner）

[次]
  Day 9    provenance インデックス、design エクスポート
  Phase 8  launch remap + ゲートウェイ（BL-003）
  BL-004/5 ECLSS+EPS 統合、EPS 3b/3c（WRS team は実装済み）

[検討 — SSOS 接合の次段階]
  BL-007   EA step ↔ SSOS 物理時間（Mock 拡充 A / upstream B / 緩和 C）

[研究]
  BL-001   base モード（創発ロール）
  BL-002   進化ペルソナ
```

詳細: [memo/scrubber_degradation/mvp_plan.md](../../scrubber_degradation/plans/mvp_plan.md)、[memo/ssos_eclss_loop/](../../../../ja/users/scenarios/ssos_eclss_loop/index.md)、[memo/backlog.md](../../../../ja/developers/index.md)。

---



## 研究メモ（`docs/ja/memo/`）


| メモ                                                                                                                      | 内容                                                            |
| ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| [ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](ssos_eclss_loop_connection_plan.md)           | SSOS ECLSS Phase 0–7 詳細・検証手順                                  |
| [ssos_eclss_loop/labeled_rule_base.md](../investigations/labeled_rule_base.md)                             | シミュレーション内 labeled 運用。必要量を積んでから上限                     |
| [ssos_eclss_loop/post_run_design_agent.md](../investigations/post_run_design_agent.md)                             | actor / designer 分離。事後 `changes` に件数上限なし                     |
| [ssos_eclss_loop/ssos_eps_ros2_connection_plan.md](../../scrubber_degradation/plans/ssos_eps_ros2_connection_plan.md)               | EPS ROS2 ブリッジ（Phase 3）                                        |
| [ssos_eclss_loop/ssos_ros2_graph_design_investigation.md](../investigations/ssos_ros2_graph_design_investigation.md) | ゲートウェイ・remap 調査                                               |
| [backlog.md](../../../../ja/developers/index.md)                                                                                           | BL-001〜BL-007（創発ロール、Phase 8、ECLSS/EPS、CLI v3 スコープ外、step 同期検討） |
| [cli_v3_plan.md](cli_v3_plan.md)                                                                                   | **CLI v3 最終** — SSOS マウント + `ea run` 1 コマンド                   |
| [homogeneous_agent_team_plan.md](../../agents/homogeneous_agent_team_plan.md)                                                   | 同種 N 体チーム設計                                                   |


---



## SSOS / One Piece 接合（現状）

```text
[ ssos_eclss_loop — Phase 0–7 完了 ]
  EclssBackend (mock | ros2) → SsosEclssLoopTeam(Team)
       ↓ JSONL + design_proposals.json（ssos_graph）
  Dashboard（storage kg / operational timeline）
  ea-loop（Docker）+ graph_rewire（クライアント remap）

[ 未接続・バックログ ]
  ROS launch remap（Phase 8）     … BL-003
  design_proposals → provenance  … Day 9
  EA step ↔ SSOS 物理同期        … BL-007（検討）
  One Piece Web UI               … スコープ外
```

One Piece 連携: [one-piece-integration.md](../../../../ja/developers/records-integrations.md)。

---



## コントリビュータ向けチェックリスト

新機能を足すとき:

1. `SimulatorProtocol` / `EclssBackend` / JSONL スキーマを変えたら [api-contracts.md](../../../../ja/developers/reference/execution.md) を更新
2. エージェント・シナリオを増やしたら [architecture.md](../../../../ja/developers/architecture.md) を更新
3. 回帰: `pytest`（全体）、scrubber は `test_scrubber_baseline.py` / `test_scrubber_with_agents.py`、ssos は `test_ssos_eclss_loop*.py`
4. SSOS コンテナ検証: `./scripts/run_ssos_eclss_loop.sh`、`run_graph_rewire_e2e.sh`（ECLSS headless 前提）
5. 完了した項目は本ファイルの「完了」へ移し、バックログは [backlog.md](../../../../ja/developers/index.md) で管理

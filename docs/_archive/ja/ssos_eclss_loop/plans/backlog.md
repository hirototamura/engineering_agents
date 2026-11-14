# 開発バックログ

## BL-003: ROS launch remap（Phase 8 — graph_rewire A） { #bl-003 }

**ステータス**: 未着手（Phase 7 クライアント remap 完了後）  
**関連**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop_connection_plan.md) Phase 7a、[ssos_ros2_graph_design_investigation.md](../investigations/ssos_ros2_graph_design_investigation.md)

### 背景

Phase 7a は **`Ros2EclssBridge` クライアント側 remap** のみ。SSOS ノード起動時の `--ros-args -r` / launch `remappings`（A）がないと **OGS↔WRS 等の内部配線は変わらない**。ハッカソン展示の主経路（ea-loop / labeled / LLM）は A なしで成立するが、scrubber 型 `add_edge` に近い物質フロー変更には A +（必要なら）ゲートウェイ rclpy が要る。

`ssos_graph.rewires` は Phase 8 でも流用可能（bridge 用と launch 用を同一 JSON から分岐生成）。

### Tier 計画

| Tier | 工数感 | 変更箇所 | 成果物 |
|------|--------|----------|--------|
| **8a PoC** | 1–2 日 | `~/dev/ssos/ssos-headless.launch.py` に手書き `remappings` 1 件 | 1 topic/service の launch remap 動作確認 |
| **8b proposals→launch** | 3–5 日 | 下表の engineering_agents + `~/dev/ssos/` | `--apply-proposals` → 次 headless 起動で remap 反映（**ECLSS 再起動必須**） |
| **8c ゲートウェイ** | 1–2 週 | `environment/ssos/gateways/`（例: grey_water_router）、launch Node 追加、衝突検出、コンテナ E2E | scrubber 型 `add_edge` に近いフロー変更 |

### 8b で触るファイル（案）

**engineering_agents**

| ファイル | 変更内容 |
|----------|----------|
| `scenario/ssos_eclss_loop/design_proposals.py` | `graph_rewire` に `target_node` / `remap_rules[]`（`public`/`backend` は bridge 用に維持） |
| `environment/ssos/launch_remap.py`（新規） | `ssos_graph.rewires` → launch `remappings` 生成 |
| `scenario/ssos_eclss_loop/scenario_run.py` | manifest 書出し |
| `scripts/ssos_container_run.sh` | manifest あり時に headless 再起動を警告 |

**~/dev/ssos/**

| ファイル | 変更内容 |
|----------|----------|
| `ssos-headless.launch.py` | 動的 `remappings` または overlay launch |
| `ssos-eclss-headless.sh` | manifest / `SSOS_LAUNCH_REMAPS` を launch に渡す |

---

## BL-004: SSOS ECLSS ループ — フォローアップ { #bl-004 }

**ステータス**: 未着手  
**関連**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop_connection_plan.md)（Phase 0–7 完了）

| 優先 | 項目 | 説明 |
|------|------|------|
| P1 | **ros2 E2E pytest（optional）** | SSOS コンテナ CI または live skip 統合テスト |
| P1 | **LLM 接続 preflight** | llm モード開始時に `OllamaClient.check_connection()` で早期 fail |
| P2 | **WRS in scenario team** | **完了。** `SsosEclssLoopTeam` が labeled / LLM で `water_recovery` を発行。`LoopMockEclssBackend.send_water_recovery_goal` はいまも `NotImplementedError`（`plant_sim` / `ros2` を使う）。 |
| P2 | **ECLSS + EPS 単一 ros2 シナリオ** | 電力危機と ECLSS を同一 run（`eclss.backend=ros2` + `eps.backend=ssos_eps`） |
| P2 | **rclpy ネイティブ ECLSS クライアント** | CLI ブリッジからの移行（レイテンシ・CI 安定性） |
| P3 | **MkDocs CI deploy** | `docs/ssos-mkdocs` ブランチ |
| P3 | **upstream CO₂ スクラバ** | SSOS ECLSS 拡張 → 新 Mock シナリオ |

### エッジケース（優先度 Low — 7d でメモ済み、未実装）

| 項目 | メモ |
|------|------|
| `co2_critical` 未使用（labeled） | ~~health は critical を評価するが labeled ルールは `co2_high` のみ~~ → **修正済（T3）**: critical 帯で ARS をエスカレート再発行 |
| One Piece provenance ヒューリスティック | operational イベントの message パース依存 |
| labeled が command failure を無視 | 次ステップのルール分岐に未反映 |
| `set_parameter` 任意パス | 本番 SSOS では allowlist 推奨 |

---

## BL-006: SSOS run 再現性・ダッシュボード強化（CLI v3 スコープ外） { #bl-006 }

**ステータス**: 未着手（CLI v3 マウント + `ea run` 完了後）  
**関連**: [cli_v3_plan.md](cli_v3_plan.md)、[scenario-ssos-eclss-loop.md](../../../../ja/users/scenarios/ssos_eclss_loop/index.md)

CLI v3 では **ホスト 1 コマンド実行と results マウント** に集中する。以下はシミュレーション／可視化レイヤで別途実装する。

### P1 — プラント初期状態（ros2 と mock）

| 項目 | 説明 |
|------|------|
| `scenario.yaml` | mock 既定は教育用スケール kg（`initial_co2_storage_kg: 1.5`；`thresholds` 参照） |
| ros2 step 0 | headless 再起動後の `/co2_storage` を `summary.plant_initial_co2_storage_kg` に記録 |
| 検証 | シナリオ目標との許容差外で fail fast（SSOS launch 設定を案内） |
| テスト | `tests/scenario/test_ssos_eclss_loop.py` の CO2 期待値更新 |
| SSOS 側 | headless 既定が期待プラント状態と食い違う場合、launch パラメータ調査（engineering_agents 単独では物理状態を捏造しない） |

**意図**: run 間で状態が残らないことは CLI（headless 再起動）で担保。ros2 プラント（ワイヤ上グラム）をブリッジ換算でシナリオ閾値と整合 — トン単位の mock リテラルではない。

### P1 — Streamlit ダッシュボード（SSOS リッチ表示）

対象: `src/tools/dashboard/ssos_views.py`, `app.py`

| セクション | 内容 |
|-----------|------|
| Run メタ | `duration_wall_s`, `plant_initial_co2_storage_kg`, ops 数 |
| 閾値ライン | CO2/O2 プロットに `co2_storage_high_kg` / `o2_storage_low_kg` |
| Ops / メッセージ | events の goal フィールド、messages タイムライン |
| Health 推移 | `health_metrics.jsonl` の折れ線 |
| 比較モード | duration・CO2 ピークの並列表示 |
| Deep link | `st.query_params` で run 名を URL から選択 |

### P2 — ドキュメント

- `ja/docs/scenario-ssos-eclss-loop.md` — headless 再起動とプラント初期 CO2 の運用説明
- 再現性チェックリスト（連続 2 run で step0 CO2 が一致すること）

---

## BL-007: SSOS ↔ EA 時間・step 同期（接続の次段階） { #bl-007 }

**ステータス**: 検討中（CLI v3 / Phase 8 とは別トラック）  
**関連**: [scenario-ssos-eclss-loop.md](../../../../ja/users/scenarios/ssos_eclss_loop/index.md)、[ssos_eclss_physical_phenomena_overview.md](../investigations/ssos_eclss_physical_phenomena_overview.md)、BL-004（WRS mock）、BL-006（run 境界の再現性）

### 背景

- **EA の `steps`** は意思決定サイクル（observe → deliberate → act）。**SSOS ros2 プラント**はウォールクロックで常時進行する。
- `LoopMockEclssBackend` だけが `advance_step()` で **1 EA step = 1 物理 tick** を保証している。
- `ea run` の headless 再起動は **run 間**の状態リセットであり、**run 内の step と SSOS 物理時間の対応ではない**。
- SSOS 現行 headless に **全体 time_scale / sim clock** はない（[space_station_os](https://github.com/space-station-os/space_station_os)）。

**結論（現時点）**: EA step を SSOS 物理時間と厳密に 1:1 対応させるのは **難易度が高い**。接合の次段階として方針を選び、バックログで検討する（**cli_v3_plan には載せない**）。

### 現行の接合モデル（維持）

| backend | step の意味 | 用途 |
| --- | --- | --- |
| `mock` | 明示 tick（`mock_dynamics`） | エージェント・閾値・LLM 比較・pytest |
| `ros2` | 瞬間スナップショット + Action 完了待ち | SSOS 接合 smoke・E2E・デモ（少数 step） |

### 方策 A — engineering_agents 内 SSOS Mock の拡充（推奨の第一候補）

本リポジトリに **SSOS 相当の統合 Mock** を置き、トピック生成・WRS/OGS/ARS 動態・EPS 連携を EA 側で一元管理する。

| 項目 | 内容 |
| --- | --- |
| スコープ | `LoopMockEclssBackend` 拡張または `SsosPlantMock` 新設。`/co2_storage` 等の契約を `eclss_topics.py` と整合 |
| WRS / OGS | mock 上で Action/Service 効果を step 同期で再現（BL-004 WRS team と接続） |
| EPS | 既存 `MockEpsBackend` / `EpsStack` との単一 tick 駆動 |
| メリット | upstream 依存なし、pytest 高速、**step = 物理 tick** を設計できる |
| デメリット | SSOS 実装との乖離リスク。契約テスト（topic 名・Action 型）の維持が必要 |

### 方策 B — SSOS upstream で sim clock / tick 同期

[space_station_os](https://github.com/space-station-os/space_station_os) を fork/clone し、`use_sim_time` + `/clock` または「EA tick まで物理停止」など **上流変更**で同期する。

| 項目 | 内容 |
| --- | --- |
| スコープ | headless launch、ノードタイマー、Crew/代謝駆動の見直し |
| メリット | 実プラントに近い物理で step 同期の可能性 |
| デメリット | 工数・メンテナンスコスト大。**やりすぎ**の可能性。Mac Docker + 実時間運用との両立 |

### 方策 C — 緩和策のみ（短期、BL-006 と重複しうる）

厳密同期は諦め、**観測契約**を強化する。

- テレメトリに poll 時刻・`step_dwell_s`（Action 後待ち）
- step 0 プラント検証（BL-006）
- ダッシュボードで wall time と step を並記

### 検討・決定事項（未スケジュール）

1. A/B/C のどれを「次の接合フェーズ」の主軸にするか（ハイブリッド: **ロジックは A、接合証明は ros2 少数 step** も可）
2. 方策 A の境界: `Ros2EclssBridge` と同じ `EclssBackend` Protocol を mock が実装するか
3. 方策 B を SSOS に issue/PR する場合の最小 API（`tick(Δt)` / pause / sim clock）
4. `scenario.yaml` に `simulation.ssos_time_model: mock_tick | ros2_snapshot` のような明示フラグが要るか

### 他バックログとの関係

| BL | 関係 |
| --- | --- |
| BL-004 | WRS team・ECLSS+EPS 統合 — 方策 A と重なる部分あり |
| BL-006 | run 境界の再現性・step0 検証 — 方策 C。step 同期の代替ではない |
| BL-003 | launch remap — 同期とは独立 |

### MVP / 開発プランとの関係

- **次の実装優先列（provenance、Phase 8 等）には入れない**
- CLI v3 完了後の **「SSOS 接合・次段階」検討トラック**として [development-plan.md](../../../../ja/developers/development/index.md) に記載

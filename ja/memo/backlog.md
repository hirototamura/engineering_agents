# Backlog — 研究・設計検討項目

MVP スコープ外だが、価値がありトラックしておくテーマ。実装優先度は [mvp_plan.md](mvp_plan.md) のロードマップに従う。SSOS 接合の未着手項目は [ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) Phase 0–7 完了後のフォローアップ。

---

## BL-001: ロールラベル付与 vs 創発ロール（Base Role）

**ステータス**: 検討中（Week-1 以降）  
**関連**: Day 4 エージェントチーム設計、lunar_agents の structured communication 実験

### 背景

運用フェーズのエージェントチーム（Monitor / Diagnostician / Operator / DesignEngineer 等）は、**人間の都合による分業のラベル化**に過ぎない可能性がある。MVP では scrubber_degradation に即した**特定ロール**を与えて異常対応を通すが、これはデモ成立のための pragmatic な選択である。

### 検討問い

| 条件 | 仮説 |
| --- | --- |
| **Labeled** — シナリオ固有の 4 ロールを明示付与 | 異常対応が速く・再現性が高い。プロンプト/ルール設計が楽。 |
| **Unlabeled** — Base Role エージェント（ロール名・役割指示なし） | テレメトリと通信履歴のみから、状況に即した役割分担が**創発**する可能性。 |
| **比較** | 創発の質（対応速度、設計変更の妥当性、コミュニケーション冗長性）を定量比較できる。 |

### 価値

- lunar_agents で示した「構造化通信・個体差→創発」の延長線上で、**ECLSS レジリエンス・ループ**文脈での検証になる
- ロールを与える/与えない設計判断の根拠データになる
- One Piece 側の「誰が設計変更を提案したか」の provenance とも接続可能

### 実験案（未スケジュール）

1. 同一 `scrubber_degradation` シナリオ・同一 Mock ECLSS
2. **Run A**: `agents.mode: labeled_rule_base`（scrubber_degradation 専用 4 ロール）
3. **Run B**: `agents.mode: base`（N 体の Base Role、ロール YAML なし）
4. 比較指標（案）:
   - 回復までの step 数（CO2 < 1000）
   - `messages.jsonl` の message_type 多様性 / 役割相当の自己記述
   - 設計変更の回数と最終 health
   - LLM 使用時: reasoning の individuality（lunar_agents 指標流用）

### MVP との関係

- **Week-1**: Labeled + rule_based のみ実装（汎用ロールフレームワークは作らない）
- **BL-001**: Week-2 以降 or ハッカソン後。Base Role 実装時に `agents.mode: base` を追加
- **BL-002** と合わせて「固定多種 / 同種 N 体 / 創発無ラベル」の三方式比較の土台になる

---

## BL-002: 進化論的ペルソナ形成（同種 vs 多種チーム）

**ステータス**: 検討中（同種 N 体チーム導入後）  
**関連**: 同種エージェントチーム再設計プラン、BL-001（創発ロール）、Day 8 persona ワークショップ、ハードウェア開発組織論

### 背景

人手でロールごとに persona を固定すると、思考・行動が型に収束し硬直しやすい（旧 `labeled_llm` / 固定4ロールでの hold 同調が一例）。MVP ではこれを避けるため **同種 N 体**（単一ペルソナ・可変人数・代表による action / 事後 design）へ移行するが、ペルソナそのものを **AI が進化・生成**する方向はまだ未着手である。

ハードウェアを開発する人間チームの代替として、どのような AI（または AI チーム）をどう組織するか——すなわち**組織論・チーム設計**の議論が本テーマの中心になる。

### 検討問い

| 軸 | 問い |
| --- | --- |
| **同種 vs 多種** | 全員同一ペルソナ（同種 N 体）と、分化したペルソナ（多種 N 体）のどちらが創発・回復・設計提案の質を高めるか。固定多種（現行4ロール）との三方式比較。 |
| **進化の単位** | 個体ペルソナ / チーム規範（charter） / 役割分担パターンのいずれを遺伝子相当とするか。 |
| **適応圧** | シミュレーション KPI（CO2 回復、電力、事後 design の妥当性）をフィットネスにどう写像するか。 |
| **人間代替組織** | 閉鎖系 ECLSS・ハードウェア開発において、人間チームのどの機能（専門分化、レビュー、代表決裁）を AI 組織が再現すべきか。 |

### 価値

- 手書き persona の硬直を超え、ラン毎・世代毎にチーム特性を更新できる
- 同種チーム（当面の MVP）と多種・創発（BL-001）の中間層として、**「誰が persona を決めるか」**の設計空間を整理できる
- 将来の One Piece / provenance と「どの世代・どの個体が設計を提案したか」の接続

### 実験案（未スケジュール）

1. **ベースライン**: 同種 N 体 + 手書き単一ペルソナ（当面実装）
2. **変種 A**: 多種 N 体 + 進化生成ペルソナ（初期集団ランダム、交叉・突然変異）
3. **変種 B**: 同種だが charter / policy のみ進化（ペルソナ本文は固定）
4. 比較: 回復 step、design 提案の採用率（人間評価）、議論多様性、硬直指標（発言 n-gram 重複率等）

### MVP との関係

- **当面**: 同種 N 体 + 手書きペルソナ（進化なし）。本項目は**実装スコープ外**
- **BL-002**: 同種チームが安定後。進化ループ・評価関数・組織設計ドキュメントから着手

---

## BL-003: ROS launch remap（Phase 8 — graph_rewire A）

**ステータス**: 未着手（Phase 7 クライアント remap 完了後）  
**関連**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) Phase 7a、[ssos_ros2_graph_design_investigation.md](ssos_eclss_loop/ssos_ros2_graph_design_investigation.md)

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

## BL-004: SSOS ECLSS ループ — フォローアップ

**ステータス**: 未着手  
**関連**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)（Phase 0–7 完了）

| 優先 | 項目 | 説明 |
|------|------|------|
| P1 | **ros2 E2E pytest（optional）** | SSOS コンテナ CI または live skip 統合テスト |
| P1 | **LLM 接続 preflight** | llm モード開始時に `OllamaClient.check_connection()` で早期 fail |
| P2 | **WRS in scenario team** | `SsosEclssLoopTeam` が WRS goal / 水サービスを labeled・LLM で操作 |
| P2 | **ECLSS + EPS 単一 ros2 シナリオ** | 電力危機と ECLSS を同一 run（`eclss.backend=ros2` + `eps.backend=ssos_eps`） |
| P2 | **rclpy ネイティブ ECLSS クライアント** | CLI ブリッジからの移行（レイテンシ・CI 安定性） |
| P3 | **MkDocs CI deploy** | `docs/ssos-mkdocs` ブランチ |
| P3 | **upstream CO₂ スクラバ** | SSOS ECLSS 拡張 → 新 Mock シナリオ |

### エッジケース（優先度 Low — 7d でメモ済み、未実装）

| 項目 | メモ |
|------|------|
| `co2_critical` 未使用（labeled） | health は critical を評価するが labeled ルールは `co2_high` のみ |
| One Piece provenance ヒューリスティック | operational イベントの message パース依存 |
| labeled が command failure を無視 | 次ステップのルール分岐に未反映 |
| `set_parameter` 任意パス | 本番 SSOS では allowlist 推奨 |

---

## BL-005: SSOS EPS ROS2 ブリッジ — フォローアップ

**ステータス**: Phase 3a 完了（PR-1〜4）、残り未着手  
**関連**: [ssos_eps_ros2_connection_plan.md](ssos_eclss_loop/ssos_eps_ros2_connection_plan.md)

### 完了済み（参照）

- `EpsBackend` / `Ros2EpsBridge` / `topic_map.py` / `build_eps_backend()`
- `request_eps_boost` **interim 3a** — BCDU `discharging` 時 `current_draw * bus_voltage` + bridge タイマー
- `scripts/run_ssos_eps_smoke.sh`

### 未着手

| 優先 | 項目 | 説明 |
|------|------|------|
| P2 | **PR-5 運用ドキュメント** | `docs/ssos-eps-integration.md`（別 PR） |
| P2 | **Phase 3b — BCDU discharge 直接呼び出し** | `/battery/battery_bms_*/discharge` サービスを bridge から呼ぶ |
| P3 | **Phase 3c — `/bcdu/operation` Action** | SSOS upstream PR。現状 README のみで未実装 |
| P3 | **Mac ホスト↔コンテナ DDS** | CycloneDDS Peers 等。当面はコンテナ内実行に限定 |
| P2 | **トピック契約の継続整合** | `eps_topics.py` と SSOS 実名（`/solar_controller/ssu_voltage_v` 等）のドキュメント同期 |
| P2 | **EPS BCDU action（scrubber 3b）** | `Ros2EpsBridge` で discharge/boost の Action 経路（現状 topic + command のみ） |

### 既知の制限（3a interim）

- `/bcdu/operation` 未実装 — discharge は SSOS 自動閾値 + bridge タイマー依存
- `support_w` は SSOS メッセージにない — bridge が watt 推定で補完
- ECLSS は scrubber 経路では引き続き `MockEclssSimulator`（ECLSS+EPS 単一シナリオは BL-004）

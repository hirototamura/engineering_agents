# CLI v3 最終プラン — SSOS ホスト 1 コマンド + マウント

> **2026-06 確定版**  
> 前提: [v2 統一 CLI](https://github.com/hirototamura/engineering_agents/blob/main/.cursor/plans/unified_simulation_cli.plan.md)（Day 8）は `ea run` / `RunSpec` / `ea job run` まで完了。  
> 利用者向け手順: [CLI ガイド](../cli.md)  
> v3 スコープ外: [backlog.md](backlog.md#bl-006)（BL-006）

---

## 北極星

1. **ホストから 1 コマンド** — `ea run ssos_eclss_loop`（`ea ssos` サブコマンドや追加 bash ラッパーはユーザーに見せない）
2. **結果はホスト** `src/experiments/results/` **に即出る**（ボリュームマウント。`docker cp` 毎回はしない）
3. **分析は Streamlit が主** — CLI `ea results` は入口（ダッシュボード強化の詳細は BL-006）

---

## ユーザーが覚えるコマンド

```bash
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50   # SSOS ros2（デフォルト）
ea run ssos_eclss_loop --backend mock --agents-mode none            # ホスト mock
ea results                                                          # 直近 run 一覧
python3 -m streamlit run src/tools/dashboard/app.py                 # 分析
```

上級者・並列ワーカー用（非宣伝）: `ea job run SPEC.json`  
**作らない**: `ea batch`, `ea bench`, `ea ssos status|sync|…`

---

## アーキテクチャ（確定）

Docker / headless / ros2 グラフは **bash**。シミュレーション本体は **既存 Python**。

| 層 | 担当 |
| --- | --- |
| ユーザー | `ea run` のみ |
| `src/tools/cli/commands/run.py` | `ssos_eclss_loop` + ros2 → 内部委譲（薄い分岐） |
| `src/tools/cli/ssos_host.py` | RunSpec 組み立て → `ssos_host_run.sh` を subprocess |
| `scripts/ssos_host_run.sh` | コンテナ確認、マウント検証、**headless 再起動**、graph poll、`docker exec` + `ea job run` |
| コンテナ内 | `PYTHONPATH=/ea/src`、`EA_RESULTS_ROOT=/ea/results`、`execute_run` |
| シミュレーション | `scenario/ssos_eclss_loop/scenario_run.py` |

`scripts/run_ssos_eclss_loop.sh` は開発者向けエイリアス（中身は `ea run` 委譲）。  
`scripts/ssos_container_run.sh` はレガシー `ea-loop` 用（コンテナ内直実行。`ea run` の再帰はしない）。

```text
ea run ssos_eclss_loop
  → ssos_host.py
  → ssos_host_run.sh
       1. docker ps / マウント検証
       2. headless 停止 → 再起動（run 間でプラント状態を残さない）
       3. ros2 graph poll
       4. docker exec: EA_RUN_IN_CONTAINER=1 ea job run job.json
  → execute_run（コンテナ内）
  → /ea/results（ホスト experiments/results にマウント）
```

**Mac ホスト DDS は使わない。** ホスト直 ros2 は行わず、SSOS は常にコンテナ内 ros2。

---

## ボリュームマウント（初回設定）

**コマンド一式**: [CLI ガイド](../../cli.md#ssos-docker-ssos_eclss_loop--ros2) / [quickstart](../ssos/quickstart.md#ssos_eclss_loop--コマンド一式mac)

```bash
./scripts/ssos/mac/ssos-run-detached.sh
```

コンテナ内環境変数:

```bash
export SSOS_CONTAINER_REPO=/ea
export EA_RESULTS_ROOT=/ea/results
export PYTHONPATH=/ea/src
```

マウント未設定時: `ssos_host_run.sh` が exit 3 + マウント例を表示。**v3 では `docker cp` フォールバックは実装しない**（設定ミスを早期検出）。

| 環境変数 | デフォルト | 用途 |
| --- | --- | --- |
| `SSOS_CONTAINER` | `ssos` | コンテナ名 |
| `EA_MOUNT_SRC` | `/ea/src` | マウント検証パス |
| `EA_MOUNT_RESULTS` | `/ea/results` | 結果ルート |
| `EA_HEADLESS_POLL_TIMEOUT_S` | `120` | headless 起動待ち |
| `EA_RUN_IN_CONTAINER` | — | コンテナ内で `ea run` が再帰委譲しないためのフラグ |

---

## `ea run` 振り分け

| 条件 | 経路 |
| --- | --- |
| `ssos_eclss_loop` + ros2（**デフォルト**） | `ssos_host_run.sh`（docker あり・`EA_RUN_IN_CONTAINER` なし） |
| `ssos_eclss_loop` + `--backend mock` | ホスト `execute_run` |
| `scrubber_degradation` 等 | ホスト `execute_run` |

`--output-dir` は ssos ros2 では非対応（`--run-id` / マウント済み `results` を使う）。

---

## CLI v3 実装スコープ（本プラン）

| 項目 | ファイル | 内容 |
| --- | --- | --- |
| ホスト orchestrator | `scripts/ssos_host_run.sh` | マウント・headless 再起動・job exec |
| Python 委譲 | `src/tools/cli/ssos_host.py` | RunSpec → bash、ホスト run_dir 解決 |
| run 分岐 | `src/tools/cli/commands/run.py` | ssos + ros2 委譲 |
| 計測 | `src/scenario/jobs/executor.py` | `summary.duration_wall_s` |
| rclpy 終了 | `src/environment/ssos/ros2_eclss_telemetry.py` | `destroy_node` + `rclpy.shutdown()` |
| results UX | `src/tools/cli/output.py`, `commands/results.py` | duration 列、dashboard 案内 |
| ラッパー | `scripts/run_ssos_eclss_loop.sh` | `ea run` 委譲 |
| コンテナ legacy | `scripts/ssos_container_run.sh` | マウントパス・`EA_RESULTS_ROOT` |
| ドキュメント | `docs/en/cli.md`, `docs/ja/cli.md` | マウント + 1 コマンド |
| テスト | `tests/tools/test_ssos_host.py` 等 | bash 委譲のモック単体テスト |

---

## スコープ外（BL-006 に移管）

シミュレーション／可視化レイヤ。CLI 完了後に別 PR で実装。

| 項目 | 内容 |
| --- | --- |
| CO2=500kg 初期値 | `scenario.yaml`、mock テスト、ros2 step0 の `plant_initial_co2_storage_kg` 記録・検証 |
| ダッシュボード強化 | 閾値ライン、ops/messages タイムライン、比較、deep link |
| シナリオ doc | `scenario-ssos-eclss-loop.md` のプラント再現性チェックリスト |

**分担**: run 間の状態リセットは CLI（headless 再起動）。目標 CO2 水準と検証はシナリオ／SSOS launch 契約（BL-006）。

---

## 並列・バッチ（業界標準に従い CLI では作らない）

各 run は `RunSpec` JSON。オーケストレーションは外部:

```bash
# 例: GNU parallel / K8s Job
ea job run /worker/jobs/job-0042.json
```

manifest YAML の `ea batch` コマンドは **実装しない**（`docs/cli.md` に段落のみ）。

---

## v2 から削ったもの（再掲）

| 案 | 判定 |
| --- | --- |
| `ea ssos` サブコマンドツリー | 不要（`ea run` に内包） |
| `tools/cli/ssos_docker.py` 厚い Python | 不要（bash に集約） |
| `ea bench` / timing 分解 | 不要（`duration_wall_s` のみ） |
| 毎回 `docker cp` sync/fetch | 不要（マウント） |
| `RunSpec.execution_target` 拡張 | 不要（シナリオ名 + backend で振り分け） |

---

## 検証（Done の定義）

```bash
# ssos-run.sh にマウント追加後
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
python3 -m streamlit run src/tools/dashboard/app.py
```

確認:

- ホスト `experiments/results/` に即ファイル出現（cp なし）
- `summary.json` に `duration_wall_s`
- 連続 2 run で headless 再起動によりプラントがリセットされる
- 終了時 `Aborted`（rclpy）なし
- `pytest` 通過

---

## 関連

| ドキュメント | 内容 |
| --- | --- |
| [unified_simulation_cli.plan.md](https://github.com/hirototamura/engineering_agents/blob/main/https://github.com/hirototamura/engineering_agents/blob/main/.cursor/plans/unified_simulation_cli.plan.md) | v2（Day 8）設計・実装記録 |
| [cli_v3_ssos_container.plan.md](https://github.com/hirototamura/engineering_agents/blob/main/.cursor/plans/cli_v3_ssos_container.plan.md) | v3 初期案（フル版。Lean に縮小して本メモが正本） |
| [eps_implementation_plan.md](scrubber_degradation/eps_implementation_plan.md) | Day 8 CLI 区切り |
| [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) | SSOS 接合 Phase 0–7 |
| [development-plan.md](../development-plan.md) | 進行中マイルストーン |

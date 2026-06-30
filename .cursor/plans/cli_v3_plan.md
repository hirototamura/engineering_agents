---
name: CLI v3 — final (mount + bash)
overview: "正本は docs/ja/memo/cli_v3_plan.md。ホスト ea run ssos_eclss_loop、マウント、内部 bash、duration_wall_s。BL-006 が CO2/ダッシュボード。"
todos:
  - id: volume-mount-docs
    content: cli.md にマウント設計、ssos_host_run.sh でマウント未設定検出
    status: completed
  - id: ssos-host-bash
    content: scripts/ssos_host_run.sh — コンテナ、headless 再起動、graph poll、ea job run
    status: completed
  - id: ea-run-delegate
    content: ea run が ssos+ros2 時に bash 委譲
    status: completed
  - id: timing-rclpy
    content: duration_wall_s + rclpy.shutdown
    status: completed
  - id: results-hint
    content: ea results duration 列と dashboard 案内
    status: completed
  - id: docs-cli
    content: docs/cli.md 更新
    status: completed
isProject: false
---

# CLI v3 最終プラン

**正本（リポジトリメモ）**: [docs/ja/memo/cli_v3_plan.md](../../docs/ja/memo/cli_v3_plan.md)

v3 Lean の確定内容は上記メモに集約。Cursor 用の要約のみここに残す。

## 北極星

1. `ea run ssos_eclss_loop` のみ（ユーザー向け 1 コマンド）
2. マウントで `experiments/results` をホスト直書き
3. Streamlit が分析の主、`ea results` は入口

## スコープ

- **CLI**: `ssos_host_run.sh`, `ssos_host.py`, `run.py` 委譲, `duration_wall_s`, rclpy shutdown, `ea results`
- **BL-006**: CO2=500kg、ros2 step0 検証、ダッシュボード強化

## やらない

`ea batch`, `ea bench`, `ea ssos` ツリー, `ssos_docker.py`, 毎回 `docker cp`

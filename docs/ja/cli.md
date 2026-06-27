# CLI ガイド

シミュレーション実行の推奨方法は統一 CLI です。インストール後:

```bash
pip install -e ".[dev]"
ea run
```

## ゴールデンパス

引数なしの `ea run` は次を実行します:

- シナリオ: `scrubber_degradation`
- エージェント: `labeled_rule_base`（Ollama 不要）
- ステップ数: `scenario.yaml` の値（デフォルト 50）

`scenario.yaml` と同じ物理のみ実行にする場合は `--agents-mode none` を指定します。

## コマンド

| コマンド | 用途 |
| --- | --- |
| `ea run [SCENARIO]` | 1回シミュレーション実行 |
| `ea scenarios` | 利用可能なシナリオ一覧 |
| `ea results [RUN_ID]` | 直近 run 一覧、または `summary.json` 表示 |
| `ea doctor` | Python・依存関係・Ollama 到達性の確認 |
| `ea job run SPEC.json` | シリアライズ済み `RunSpec` を実行（クラスタワーカー互換） |
| `ea --version` | CLI バージョン表示 |

モジュール形式:

```bash
python3 -m tools.cli run scrubber_degradation --agents-mode none
```

## よく使うフラグ

```bash
ea run scrubber_degradation --agents-mode labeled_rule_base --steps 30
ea run ssos_eclss_loop --backend mock --agents-mode none --steps 4
ea run scrubber_degradation --set simulation.steps=10
ea run --dry-run --write-spec /tmp/job.json
ea job run /tmp/job.json
```

詳細は [en/docs/cli.md](../en/docs/cli.md) を参照してください。

## 結果の確認

```bash
ea results
python3 -m streamlit run src/tools/dashboard/app.py
```

## SSOS Docker（`ssos_eclss_loop` + ros2）

ホストからは **`ea run ssos_eclss_loop` だけ**でよい。コンテナ確認・headless 再起動・ジョブ実行は内部 bash が担当する。

**初回のみ** — SSOS コンテナ起動時にマウントを追加（`~/dev/ssos/ssos-run.sh` 等）:

```bash
REPO_ROOT=/path/to/engineering_agents
docker run -it --name ssos \
  -v "$REPO_ROOT/src:/ea/src" \
  -v "$REPO_ROOT/src/experiments/results:/ea/results" \
  ghcr.io/space-station-os/space_station_os:latest
```

| マウント | 用途 |
| --- | --- |
| `src` → `/ea/src` | コンテナ内でコード参照（毎回 `docker cp` 不要） |
| `experiments/results` → `/ea/results` | 成果物がホストに即書き込まれる |

Mock（Docker 不要）:

```bash
ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base --steps 8
```

設計メモ: [memo/cli_v3_plan.md](memo/cli_v3_plan.md)（v3 最終プラン）。

詳細は [en/cli.md](../en/cli.md) の SSOS セクションを参照。

## 並列実行（将来）

各シミュレーションは `RunSpec` JSON で表現します。将来のバッチランナーはワーカーごとに次を実行します:

```bash
ea job run /worker/jobs/job-0042.json
```

## レガシーエントリポイント

以下も同じ実行パスに委譲されます:

- `python3 src/scripts/run_mock_eclss.py`
- `python3 -m scenario.ssos_eclss_loop.scenario_run`
- `from scenario.runner import run_scenario`

---
name: Unified Simulation CLI
overview: 分散している実行経路を `ea` 単一CLIに統合し、誰でも1コマンドでシミュレーションを完走できるUXを実現する。並列数千回実行は今回実装しないが、RunSpec ベースの実行契約を scenario 層に置き、将来のGPUクラスタ／バッチワーカーが同じコードパスを再利用できる設計にする。
todos:
  - id: jobs-layer
    content: scenario/jobs に RunSpec・resolve_run_directory（既存2シナリオから抽出）・execute_run を実装
    status: pending
  - id: refactor-run-dir
    content: scrubber/ssos の scenario_run.py で重複している run_dir 解決を resolve_run_directory に置換
    status: pending
  - id: cli-mvp
    content: "tools/cli MVP: run / scenarios / --version + Rich outcome（Typer）"
    status: pending
  - id: cli-extended
    content: "tools/cli 拡張: results / doctor / job run・write-spec / shell completion"
    status: pending
  - id: pyproject-entry
    content: pyproject.toml に typer・rich 依存と ea コンソールスクリプトを追加
    status: pending
  - id: migrate-wrappers
    content: run_mock_eclss.py と ssos_eclss_loop main() を execute_run に委譲
    status: pending
  - id: tests
    content: RunSpec round-trip・resolve 単体・CLI E2E（--steps 2, tmp_path）を追加
    status: pending
  - id: docs
    content: en/docs/cli.md + ja/docs/cli.md 作成、README・development-plan を ea run 中心に更新
    status: pending
isProject: false
---

# 統一シミュレーション CLI 設計プラン（v2 — 批判的レビュー反映）

> リポジトリ内コピー: [`.cursor/plans/unified_simulation_cli.plan.md`](.cursor/plans/unified_simulation_cli.plan.md)

## 批判的レビューで見つかった問題と対応

| 問題 | 深刻度 | 対応 |
|------|--------|------|
| `resolve.py` を新設するが、両 `scenario_run.py` に **同一の run_dir 解決ロジックが既に重複** している。executor 側だけ centralize すると二重実装になる | 高 | `resolve_run_directory()` を **両シナリオから抽出して共有** し、executor はそれを呼ぶだけにする（リファクタ必須タスク） |
| サブコマンド7個は「無駄のないCLI」と矛盾。`dashboard` は Streamlit 子プロセス管理（ポート競合・ブロック）の別問題 | 中 | **フェーズ分け**: MVP は `run` + `scenarios` のみ。`dashboard` サブコマンドは **延期**（Outcome カードにコマンドを表示するだけ） |
| `extensions: dict` は型安全でなく、シナリオ固有オプションが増えると腐る | 中 | `RunSpec.apply_proposals_path: Path \| None` を **明示フィールド** に |
| `results_base` が両シナリオでハードコード。クラスタでは共有 FS 前提 | 高 | `EA_RESULTS_ROOT` 環境変数 + `RunSpec.results_root` |
| `scenario.yaml` デフォルトは `mode: none` だが CLI は `labeled_rule_base` — 説明不足 | 低 | **CLI はデモ用に意図的に上書き** と明記 |
| シナリオループへの `on_step` コールバックは侵襲的 | 中 | **v1 延期**。開始パネル + 完了 Outcome + 所要時間のみ |
| `--interactive` は TTY 判定・テスト困難 | 低 | **v1 スコープ外** |
| `ea job write-spec` 独立サブコマンドは重複 | 低 | `ea run --write-spec job.json --dry-run` に統合 |
| 並列時の再現性（seed）が RunSpec にない | 中 | `RunSpec.seed` を追加（v1 は summary 記録のみ） |
| 終了コードの規約がない | 中 | `0/1/2/3` を定義 |

---

## フェーズ分け

### Phase A — MVP（必須）

- `ea run [SCENARIO]`, `ea scenarios`, `ea --version`
- `RunSpec`, `resolve_run_directory`（既存から抽出）, `execute_run`
- フラグ: `--agents-mode`, `--steps`, `--run-id`, `--output-dir`, `--set`, `--override-file`, `--json`, `--quiet`
- Rich: 開始パネル + 完了 Outcome カード

### Phase B — 拡張（MVP 直後）

- `ea results`, `ea doctor`, `ea job run`, `ea run --write-spec --dry-run`
- `--backend`, `--apply-proposals`, `--no-recreate`
- Typer shell completion, `EA_RESULTS_ROOT`

### 延期（v2）

- `ea dashboard` サブコマンド、`--interactive`、ステップ進捗バー、`ea batch submit`

---

## RunSpec（改訂）

```python
@dataclass
class RunSpec:
    scenario: str
    overrides: dict[str, Any] | None = None
    output_dir: Path | None = None
    run_id: str | None = None
    results_root: Path | None = None
    recreate_output: bool = True
    seed: int | None = None
    apply_proposals_path: Path | None = None
```

## 終了コード

| Code | 意味 |
|------|------|
| 0 | 成功 |
| 1 | シミュレーション実行中の例外 |
| 2 | 引数・override パースエラー |
| 3 | 環境エラー（Ollama 不通等） |

## ゴールデンパス

```bash
ea run   # scrubber_degradation + labeled_rule_base（Ollama 不要）
```

## 検証

```bash
ea run --steps 2
pytest tests/scenario/test_run_spec.py tests/tools/test_cli.py
pytest  # 全回帰
```

詳細は上記セクションおよび artifacts 版プラン全文を参照。

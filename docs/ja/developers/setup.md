# 開発環境を用意する

Python 3.11 以降を使います。ドキュメントの確認ワークフローは Python 3.12 を使用します。依存パッケージと追加グループの定義は [pyproject.toml](https://github.com/hirototamura/engineering_agents/blob/main/pyproject.toml)にあります。

## インストールと参照先の確認

リポジトリのルートで実行します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -c "import scenario.runner; print(scenario.runner.__file__)"
python -m tools.cli --help
```

表示されたモジュールのパスが、このチェックアウトの `src/` を指すことを確認します。別のクローンの編集可能インストールが残っていると、異なるコードを調査・実行することがあります。原因調査には `PYTHONPATH=src python ...` を使えます。`ea` と `python -m tools.cli` は同じ Typer アプリケーションを呼び出します。

## 基準となる確認

```bash
python -m pytest --ignore=tests/e2e
python -m mkdocs build --strict
```

最初のコマンドは通常のテスト群です。`tests/e2e` の実 SSOS テストには Docker、ROS2、`SSOS_E2E=1` が必要で、環境を別に用意します。追加パッケージやハードウェアがなければスキップされるシミュレータのテストもあります。変更対象に関係するスキップは内容を確認してください。

変更に必要な依存だけを追加します。ネイティブ MuJoCo は `.[mujoco]`、固定バージョンの MJX/JAX は `.[gpu]`、One Piece パッケージは `.[onepiece]` です。数値計算パッケージの要件が異なるため、必要に応じて適切な別環境を使います。LLM モードには設定済みプロバイダへの接続も必要です。通常のソース・文書の変更のために実験を実行する必要はありません。

モジュールを移す前に[アーキテクチャ](architecture.md)を読み、[貢献手順](contributing.md)と[シナリオ別の実装ガイド](scenarios/index.md)から変更に必要な回帰確認を選びます。利用者向けの前提条件と実行手順は[利用者ドキュメント](../users/index.md)を参照してください。

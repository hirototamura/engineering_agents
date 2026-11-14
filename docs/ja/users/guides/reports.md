# レポートライブラリを使う

レポートライブラリは、ワークスペースにある既存の HTML レポートを発見し、検索可能なカタログを作ります。証拠の閲覧用であり、シミュレーションの実行や元の証拠の置換は行いません。

## カタログを生成・配信する

プロジェクトフォルダを含むワークスペースを明示します。

```bash
PYTHONPATH=src python -m tools.cli reports build --workspace /path/to/workspace
PYTHONPATH=src python -m tools.cli reports serve --workspace /path/to/workspace --port 8765 --open
```

`build` はワークスペース内に `reports/index.html`、言語別ページ、`reports/catalog.json` を生成します。`serve` は再読み込み時に再走査し、`http://127.0.0.1:8765/reports/index.html` で開きます。Ctrl-C で終了します。カタログ生成は元の HTML レポートを編集しません。

`--workspace` を省略した場合は `EA_REPORT_WORKSPACE` を使います。それもなければ現在のディレクトリを使います。ただし `engineering_agents` と同じ親に `one-piece` がある場合は親を選びます。再現可能な利用には明示指定が分かりやすくなります。

## 任意の翻訳とサムネイル

```bash
PYTHONPATH=src python -m tools.cli reports translate --workspace /path/to/workspace --prepare-only
PYTHONPATH=src python -m tools.cli reports verify --workspace /path/to/workspace
PYTHONPATH=src python -m tools.cli reports capture --workspace /path/to/workspace
```

翻訳の準備はモデルへ接続せず文章量を数えます。実際の翻訳は `--endpoint`（既定 `http://127.0.0.1:18001`）と翻訳処理に固定されたモデルを使い、シミュレーションの LLM 設定は継承しません。派生した言語別表示と翻訳マニフェストを生成します。サムネイルにはブラウザ撮影環境が必要です。詳細は `PYTHONPATH=src python -m tools.report_library.translate_reports --help` など、処理ごとのモジュールのヘルプで確認します。

共有前に翻訳したラベルを元の証拠と照合し、`verify` を実行してください。翻訳は新しい測定を追加せず、元の実験の妥当性も変えません。指標の意味は対象の[シナリオ](../scenarios/index.md)に戻って確認します。

## どの層を読んでいるかを確認する

| 層 | 代表的な成果物 | 意味 |
| --- | --- | --- |
| 測定の元記録 | 実行 JSON/JSONL と凍結入力 | 監査する条件と観測 |
| シナリオのレポート | `evaluation.html`、キューブ campaign レポート | 宣言した評価の表示 |
| 読みやすくした派生物 | 翻訳レポートと manifest | 元の測定は同じで、言語が異なる |
| カタログ | `reports/catalog.json`、HTML | レポート横断の発見と移動 |
| サムネイル | レポートの撮影画像 | 全記録の代わりにはならないプレビュー |

カタログで見つけたら、レポートから元の証拠へ進みます。サムネイルだけでは欠損ケースや分母の変更が見えず、翻訳が inconclusive を解消することもありません。

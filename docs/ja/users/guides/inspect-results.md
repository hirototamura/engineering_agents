# 実行の証拠を確認する

まずコマンドが表示した出力ディレクトリを開きます。既定の実験ルートにある実行は次のように確認できます。

```bash
PYTHONPATH=src python -m tools.cli results --limit 10
PYTHONPATH=src python -m tools.cli results quickstart-run2
PYTHONPATH=src python -m tools.cli results --track balancing_cube --limit 10
```

`results` は `summary.json` を読み、再評価は行いません。連鎖実行の親は `chain_summary.json` を直接読みます。独自の出力先を使った場合は、既定ルートの一覧に出ると仮定せず、そのディレクトリを開いてください。

## 証拠を順に確認する

1. シナリオ、バックエンド、モード、観測期間、要求、保存設定を確認する。
2. 実際に消費した設計を特定する。実行に添付された提案は、次の設計を表す場合がある。
3. 評価状態と invalid・適用対象外・inconclusive の理由を読む。
4. 重要な値をテレメトリとイベントへたどり、条件を揃えて比較する。

記録の所在は[成果物リファレンス](../reference/artifacts.md)で確認します。指標と限界は[スクラバー](../scenarios/scrubber_degradation/results.md)、[ECLSS](../scenarios/ssos_eclss_loop/results.md)、[キューブ](../scenarios/balancing_cube/results.md)の結果ページが定義します。

## ビューアと元記録を行き来する

任意の ECLSS Streamlit ダッシュボードは実験ファイルを読みます。

```bash
PYTHONPATH=src python -m streamlit run src/tools/dashboard/app.py
```

ECLSS は `evaluation.html` と、周辺の実行を確認できる `evaluation_browser.html` も出力します。[レポートライブラリ](reports.md)はワークスペースの HTML 証拠をまとめます。

空のストリームは該当イベントがなかった可能性があります。一方、summary が欠損または不正なら、結果の読み取り失敗です。部分的な点数は 0 点ではありません。同一ステップの複数行が操作前と `post_ops` を表すことがあるため、JSONL の行数をシミュレーション区間数にしないでください。

## 主張から入力へ逆にたどる

| レポートの表現 | 次に読むもの | 受け入れる前の確認 |
| --- | --- | --- |
| 「回復した」 | テレメトリと受理した操作・イベント | シナリオの回復定義と観測窓 |
| 「点数が上がった」 | 両方の評価記録と実効入力 | 同じ採点、単位、要求、条件か |
| 「設計を適用した」 | 消費済み提案・コンパイル済み設定 | 提案値が実際にシミュレータへ入ったか |
| 「数値的に確認した」 | 独立検証とバックエンド比較 | ケースの完全性、保存制御器と条件の一致 |
| 「Before/After」 | 元の実行とプレビュー表示 | After は再シミュレーションか、提案グラフだけか |

保存済みの[スクラバーダッシュボード解説](../scenarios/scrubber_degradation/results.md#read-the-dashboard)は、2 実行の比較、ステップ再生、未検証の構造プレビューを示します。[ECLSS の過去例](../scenarios/ssos_eclss_loop/results.md#historical-four-chain-record)は、点数増加をそのまま設計改善と呼べない採点変更を示します。[キューブの証拠](../scenarios/balancing_cube/results.md)はケース合否、単一指標、数値一致を分けます。

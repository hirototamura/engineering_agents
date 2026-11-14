# ECLSS の設計を実行・比較する

ローカルの引き渡し動作は [mock クイックスタート](../../quickstart.md)を使います。プラントによる証拠は基本インストールで取得できます。両モードがラベル付きまたは無効なら plant_sim に ROS2 もモデルサービスも必要ありません。

## 1 回のベースラインを測定する

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --actor-mode labeled_rule_base --design-mode labeled_rule_base \
  --steps 50 --run-id plant-baseline-01 --set iteration.enabled=false --dry-run --json
```

計画を確認して `--dry-run --json` を外します。出力を保持し、提案を適用する前に `summary.json` と `evaluation.json` を確認してください。

## レビューした提案を適用する

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --actor-mode labeled_rule_base --design-mode labeled_rule_base \
  --steps 50 --run-id plant-applied-01 --set iteration.enabled=false \
  --apply-proposals experiments/eclss/results/plant-baseline-01/design_proposals.json
```

初期条件、閾値、観測期間、故障予定、評価バージョンを揃えます。暫定提案なら理由を読んでから `--approve-provisional` を追加します。適用はメモリ上の設定を変え、消費済みスナップショットを保存します。同梱 YAML は編集しません。ドメインやバックエンドが非対応の変更は失敗します。既定では状態で禁止された提案も拒否しますが、手動の `--approve-provisional` は `rejected_final` も含めて状態ゲートを迂回し、設計範囲を保証しません。使用前に[採用の限界](../../guides/design-iterations.md)を確認してください。

提案の文章だけでなく、適用設定と観測を比較してください。容量変更の効果には plant_sim が必要です。mock は操作プロファイルや引き渡しを確認できますが、拡大プラントの動作を立証できません。

## 連鎖実行する

[設計の反復](../../guides/design-iterations.md)で回数を限定した自動実行と対比較リプレイを行えます。以前の子実行とメモリを保持するには新しい連鎖 ID を使います。`--no-recreate` は連鎖の再開機能ではありません。

## ROS2 SSOS を準備する

稼働する Docker daemon と事前構築済み SSOS image を使います。macOS では Docker Desktop または Colima を利用できます。リポジトリのルートから、同梱 helper で image を取得し、常駐コンテナを作ります。

```bash
bash scripts/ssos/mac/ssos-run-detached.sh
PYTHONPATH=src python -m tools.cli doctor
```

helper は既存の `ssos`（または `SSOS_CONTAINER_NAME`）コンテナを置換します。必要な作業がある場合は別名を選んでください。リポジトリの `src` を `/ea/src`、`experiments/eclss/results` を `/ea/results` にマウントし、`scripts/ssos/` 内のスクリプトを `/root/ssos-container-setup.sh`、`/root/ssos-eclss-headless.sh`、`/root/ssos-headless.launch.py`、`/root/ssos-eps.launch.py` にマウントします。他のホストも同等の image・mount・起動処理が必要です。停止しただけのコンテナには再作成でなく `docker start ssos` を使えます。

マウント確認後、ホストから実行します。

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend ros2 --actor-mode labeled_rule_base --design-mode labeled_rule_base \
  --steps 50 --run-id ros2-review-01 --set iteration.enabled=false
```

ホスト runner は毎回 headless シミュレーションを再起動し、1 コンテナにつき 1 実行に制限します。マウント済みルートで `--run-id` を使います。ホスト ROS2 は `--output-dir` とリポジトリの `experiments/eclss/results` 以外のルートを拒否します。異なる `EA_RESULTS_ROOT` は解除してください。ROS2 は plant_sim 用の完全スコアカードの対象ではありません。

完了とは、ベースラインと適用後の証拠を残し、[評価状態と限界](results.md)を説明できることです。終了コードや肯定的な説明だけでは検証になりません。

## 必要な証拠に合う実行経路を選ぶ

| 作業 | backend と実行形態 | 完了の証拠 |
| --- | --- | --- |
| 引き渡し確認 | mock、別 ID の単一実行 2 回 | 消費済み提案と変更した実効入力 |
| 容量比較 | plant_sim、条件を揃える | 新規テレメトリ、妥当な評価、適用容量 |
| 容量探索 | plant_sim の連鎖 | 番号付き実行、選択した測定設計、リプレイ状態 |
| SSOS 操作確認 | ROS2、ホスト・コンテナで 1 回 | 資源テレメトリと操作の受理・拒否 |

短い mock は接続確認に適していますが、期間を延ばしてもプラント検証にはなりません。ROS2 action の完了も、plant_sim 専用の生存採点を適用可能にはしません。終了コードを証拠に使う前に経路を選びます。

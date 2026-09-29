# Engineering Agents — 宇宙機ECLSSの設計をAIエージェントで検証する

[English README](README.md) · [ドキュメント](docs/ja/index.md) · [実験記録](docs/ja/results.md) · [解析データ](docs/data) · [エージェント設計](docs/ja/agent-design.md)

**詳細な成果報告:** [技術説明](docs/ja/eclss_ai_agent_technical_report_04.md)（50人サバイバルの4段階実験、創発の可視化）

Engineering Agents は、宇宙機の環境制御・生命維持システム（ECLSS）を題材に、AIエージェントが設計を改善できるかを検証するシミュレーション環境です。

このシミュレーションの特徴は、次の4点です。

- **SSOSベースの物理シミュレーションで検証する。** 空気・酸素・水の収支、装置容量、質量、コストを、単なるスコアではなく物理状態として扱います。（SSOSをそのまま使わず、部分的に簡略化したシミュレーションモデル）
- **宇宙機ECLSSという複雑系を題材にする。** CO2除去、O2生成、水再生が互いに関係するため、1つの装置だけを良くしても全体の設計は成立しません。
- **生存率だけでなく、コスト・重量とのトレードオフを解く。** 50人を生かすことを最優先にしつつ、過大な装置を積めば質量とコストで不利になります。性能だけで勝つ問題ではなく、制約下で成立する設計を探す問題です。
- **設計案をシミュレーションで検証し、次の設計に戻す。** エージェントが提案した設計を再シミュレーションし、その結果を次のiterationの入力にします。

---

## 何をシミュレーションするか

50人の乗員がいる宇宙居住区で、ECLSSの能力が不足した状態から始めます。設計エージェントはランの結果を見て、次のランで使うECLSSの設計値を提案します。

設計対象は、まず次の3変数です。

| 変数 | 意味 |
| --- | --- |
| ARS | CO2除去能力 |
| OGS | O2生成能力 |
| WRS | 水再生能力 |

ランの結果は、まず**50人中何人が生存したか**で見ます。そのうえで、設計を100点満点のスコアカードで評価します。生存数だけでなく、TCL（最初の乗員喪失までの時間）、生存環境、資源回復、コスト、質量、操作/物理応答も点数に入れます。

![評価スコアカードの配点](docs/images/results/report02_01_scorecard_pie.png)

つまり、全員を生かせても、過大な装置を積めばコスト・質量で不利になります。このシミュレーションでは、「生存できること」と「軽く、安く成立すること」の両方を見ます。

---

## 解析条件

今回の解析は、同じ世界・同じ50人の乗員・同じ初期条件に対して、50周の design→verify 連鎖を複数回走らせたものです。

| 項目 | 条件 |
| --- | --- |
| シナリオ | `ssos_eclss_loop` |
| 乗員数 | 50人 |
| 周回数 | 1連鎖あたり50 iteration |
| 乗員代謝 | NASA BVADベース。1人1日あたり CO2 1.04 kg、O2 0.84 kg、水 2.28 kg |
| 物理モデル | CO2 / O2 / H2O の質量収支、O2生成時の水消費、SabatierによるCO2消費 |
| backend | `plant_sim` |
| actor | `none` / `labeled_rule_base` / `llm` |
| 評価 | 物理整合性ゲート、乗員生存、TCL、生存環境、資源回復、コスト、質量、操作/物理応答 |
| 生ログ | [experiments/runs/](experiments/runs) |
| 解析済みデータ | [docs/data/](docs/data) |
| 解析手順 | [experiments/README.md](experiments/README.md) |

評価では、物理的に成り立たないランを低スコアにするのではなく、採点対象外にします。質量保存、在庫の非負性、装置能力上限、故障時の不自然な処理などをチェックします。

---

## 結果の概要

現行リポジトリには、4本の50周連鎖の解析結果が入っています。段階③以降は採点式を変えているため、スコアを段階①②と単純比較しないでください。生存者数、巻き戻り回数、提案の完全性、ユニーク設計数は比較できます。

| | 段階① 初期 | 段階② 連鎖記憶 | 段階③ 採点基準変更 | 段階④ 監査パネル |
| --- | ---: | ---: | ---: | ---: |
| 最終生存者 | 34/50 | 50/50 | 50/50 | 50/50 |
| 0/50 の周 | 12 | 1 | 1 | 1 |
| 3項目そろった提案 | 38/50 | 50/50 | 50/50 | 50/50 |
| ユニーク設計数 | 39 | 11 | 17 | 9 |
| 最高 / 平均スコア | 66.18 / 61.71 | 66.36 / 65.94 | 84.23 / 83.34 | 84.03 / 82.59 |

![4段階の生存者数とスコア](docs/images/results/ssos_phase1_phase2_phase3_survival_score_trend.svg)

主な読み取りは次の通りです。

1. 段階①は探索能力の失敗ではなく、状態継承の失敗でした。途中で全員生存の設計に到達しても、次の周で部分提案が入り、ARS/OGSがベースラインへ戻ることがありました。
2. 4 KBの連鎖記憶を入れると、致命的な巻き戻りは大きく減りました。一方で探索範囲は狭くなりました。
3. 旧採点では、全員が死ぬ初期設計にコスト・質量の満点ラインが置かれていました。そのため、生存可能な設計が不当に重く高く見えていました。
4. 採点基準の変更でスコアは上がりましたが、総質量・総コストが同じだけ改善したわけではありません。
5. 監査パネルは危険な設計を止めましたが、探索も止めやすくなりました。

詳細は [実験記録](docs/ja/results.md) を参照してください。

---

## 解析データ

README本文には結果の要点だけを置き、詳細はデータと実験記録に分けています。

| リンク | 内容 |
| --- | --- |
| [docs/ja/eclss_ai_agent_technical_report_04.md](docs/ja/eclss_ai_agent_technical_report_04.md) | 技術説明（成果報告） |
| [docs/ja/results.md](docs/ja/results.md) | 実験結果の説明 |
| [docs/data/](docs/data) | 周回ごとの解析済みCSV / JSON |
| [docs/data/README.md](docs/data/README.md) | データ列の説明 |
| [docs/images/results/](docs/images/results) | 図表 |
| [experiments/runs/](experiments/runs) | 4本の連鎖の生ログ |
| [experiments/analysis/](experiments/analysis) | 解析スクリプト |
| [experiments/README.md](experiments/README.md) | 再解析手順 |

再解析の最後は `diff` で確認できます。

```bash
cd experiments
for f in runs/*.tar.gz; do tar -xzf "$f" -C runs/; done
python3 analysis/analyze_ssos_iter.py --root runs/phase3-rescored --prefix phase3
diff outputs/phase3_iteration_metrics.csv ../docs/data/phase3_iteration_metrics.csv
```

---

## クイックスタート

必要なものは Python 3.11+、Git、ハッカソンで提供されたGPU環境へのVPN接続です。設計エージェントは、VPN越しにGPU上のvLLM endpointへリクエストを送ります。

> 注: GPU/VPNを使う手順は、ハッカソンのGPU使用期間中だけ有効です。期間外に動かす場合は、別途LLM endpointを用意して `agents.yaml` または `--set` で接続先を変更してください。

まずリポジトリを取得し、Python環境を作ります。

```bash
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
ea doctor
```

Windows PowerShell:

```powershell
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m tools.cli doctor
```

次に、ハッカソンで配布されたVPNプロファイルでGPU環境へ接続します。接続後、vLLM endpointに届くことを確認します。

```bash
curl http://10.10.0.108:8001/v1/models
```

Windows PowerShell:

```powershell
Invoke-RestMethod http://10.10.0.108:8001/v1/models
```

設計ループを回します。`agents.yaml` の既定設定では、設計エージェントがGPU上のvLLM endpointを使います。

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --iterate 10 --llm-provider vllm
```

1回だけ試す場合:

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --steps 72 --llm-provider vllm
ea results
```

GPU endpointが配布時の値と違う場合は、接続先を明示します。

```bash
ea run ssos_eclss_loop --backend plant_sim --actor-mode labeled_rule_base --design-mode llm --iterate 10 --llm-provider vllm --set agents.design.llm.base_url=http://<GPU_VPN_IP>:8001/v1
```

ダッシュボードを見る:

```bash
python3 -m streamlit run src/tools/dashboard/app.py
```

---

## 結果の出力先

1回のランは `src/experiments/results/<run_id>/` に保存されます。

```text
telemetry.jsonl              stepごとのプラント状態
messages.jsonl               エージェントの発話・推論
design_decision_state.json   設計エージェントに見せた情報と応答
design_proposals.json        次周へ渡した設計値
evaluation.json              評価結果
summary.json                 ラン概要
```

連鎖実行では、周回ごとのディレクトリに加えて `compact_chain_memory.json` と `chain_summary.json` が保存されます。

---

## アーキテクチャ

```text
tools/cli        ea run / scenarios / results / doctor
scenario/        シナリオごとのstepループ、設計ツール、評価、連鎖記憶
core/            エージェント、ペルソナ、メモリ、LLM client、JSON parsing
environment/     ECLSS backend: mock / plant_sim
```

詳しくは [アーキテクチャ](docs/ja/architecture.md) と [API契約](docs/ja/api-contracts.md) を参照してください。

---

## ドキュメント

| 内容 | 日本語 |
| --- | --- |
| 技術説明 | [docs/ja/eclss_ai_agent_technical_report_04.md](docs/ja/eclss_ai_agent_technical_report_04.md) |
| 概要 | [docs/ja/overview.md](docs/ja/overview.md) |
| 実験記録 | [docs/ja/results.md](docs/ja/results.md) |
| エージェント設計 | [docs/ja/agent-design.md](docs/ja/agent-design.md) |
| 拡張ガイド | [docs/ja/extending.md](docs/ja/extending.md) |
| ロードマップ | [docs/ja/roadmap.md](docs/ja/roadmap.md) |
| 実装仕様 | [docs/ja/specs/index.md](docs/ja/specs/index.md) |

---

## 現時点の課題

- 段階②以降、探索がWRS中心に寄っています。ARS/OGSの近傍探索はまだ十分ではありません。
- 採点基準の変更と、物理設計そのものの改善を分けて表示する必要があります。
- 段階④の監査は危険な候補を止めましたが、探索を狭める副作用があります。
- 現時点の結果は、モデル1つ、シード1つ、連鎖4本の実験です。統計的な結論には追加実験が必要です。

次に見るべき点は、実測下限を使う `floor_probe.py` 導入後に、探索がWRS以外へ広がるかです。

---

## License

[Apache License 2.0](LICENSE.txt) — Copyright 2026 One Piece Engineering

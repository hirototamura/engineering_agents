# SSOS ECLSS 解析手順書

この手順書は、他の人のCursor環境で、SSOS ECLSSの50 iteration結果から同じ比較レポート・CSV・SVGを再生成するためのものです。

対象は以下の4段階です。

| 段階 | 入力データ | 意味 |
|---|---|---|
| 段階① 初期 | `phase1-no-chain-memory.tar.gz` | chain memoryなしの初期実装 |
| 段階② 記憶あり改善 | `phase2-chain-memory.tar.gz` | `compact_chain_memory.json` をiteration間で保持 |
| 段階③ 記憶+評価変更 | `phase3-rescored.tar.gz` | 記憶あり + Cost/Mass評価指標を再調整 |
| 段階④ 監査パネル | `phase4-multiagent.tar.gz` | 記憶+再採点 + 設計者1・監査者3の item-veto |

## 1. 前提

必要なもの:

- Python 3.11+
- Git
- リポジトリ: `hirototamura/engineering_agents`
- 追加済みの解析ツール一式

想定されるリポジトリ構成:

```text
engineering_agents/
  experiments/
    README.md
    analysis/
      analyze_ssos_iter.py
      make_comparison_trend.py
      make_parameter_comparison.py
      make_score_group_components.py
      make_score_components_split.py
      summarize_three_way_inputs.py
    runs/
      phase1-no-chain-memory.tar.gz
      phase2-chain-memory.tar.gz
      phase3-rescored.tar.gz
    outputs/                 # 再生成結果。gitignoredでOK
  docs/
    data/
      README.md
      phase1_iteration_metrics.csv
      phase2_iteration_metrics.csv
      phase3_iteration_metrics.csv
      phase4_iteration_metrics.csv
      ...
    images/
      results/
        ssos_phase1_phase2_phase3_survival_score_trend.svg
        ssos_phase1_phase2_phase3_parameter_trends.svg
        phase1_score_components_grouped.svg
        phase2_score_components_grouped.svg
        phase3_score_components_grouped.svg
        phase4_score_components_grouped.svg
        phase1_score_components_stacked_split.svg
        phase2_score_components_stacked_split.svg
        phase3_score_components_stacked_split.svg
        phase4_score_components_stacked_split.svg
```

## 2. 解析データを展開する

リポジトリルートから `experiments/` に移動します。

```bash
cd experiments
```

Linux / macOS / Git Bash:

```bash
for f in runs/*.tar.gz; do
  tar -xzf "$f" -C runs/
done
```

Windows PowerShell:

```powershell
Get-ChildItem runs\*.tar.gz | ForEach-Object {
  tar -xzf $_.FullName -C runs\
}
```

展開後、以下のディレクトリが存在することを確認します。

```text
experiments/runs/phase1-no-chain-memory/
experiments/runs/phase2-chain-memory/
experiments/runs/phase3-rescored/
experiments/runs/phase4-multiagent/
```

各ディレクトリには `chain_summary.json` と `01/` から `50/` のiterationディレクトリがあるはずです。

## 3. iterationメトリクスを抽出する

各段階のchain結果から、CSV・JSON・単独SVGを生成します。

```bash
python3 analysis/analyze_ssos_iter.py --root runs/phase1-no-chain-memory --prefix phase1
python3 analysis/analyze_ssos_iter.py --root runs/phase2-chain-memory    --prefix phase2
python3 analysis/analyze_ssos_iter.py --root runs/phase3-rescored        --prefix phase3
python3 analysis/analyze_ssos_iter.py --root runs/phase4-multiagent      --prefix phase4
```

Windows PowerShellで日本語表示が崩れる場合:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python analysis\analyze_ssos_iter.py --root runs/phase1-no-chain-memory --prefix phase1
python analysis\analyze_ssos_iter.py --root runs/phase2-chain-memory    --prefix phase2
python analysis\analyze_ssos_iter.py --root runs/phase3-rescored        --prefix phase3
python analysis\analyze_ssos_iter.py --root runs/phase4-multiagent      --prefix phase4
```

主な生成物:

```text
experiments/outputs/phase1_iteration_metrics.csv
experiments/outputs/phase2_iteration_metrics.csv
experiments/outputs/phase3_iteration_metrics.csv
experiments/outputs/phase4_iteration_metrics.csv
experiments/outputs/phase1_iteration_findings.json
experiments/outputs/phase2_iteration_findings.json
experiments/outputs/phase3_iteration_findings.json
experiments/outputs/phase4_iteration_findings.json
```

## 4. 4段階比較グラフを生成する

### 生存者数・スコア推移

段階①-④を重ねて、生存者数と評価スコアの推移を確認します。

```bash
python3 analysis/make_comparison_trend.py
```

生成物:

```text
experiments/outputs/ssos_phase1_phase2_phase3_survival_score_trend.svg
```

見るポイント:

- 段階①は途中で生存者数が崩れていないか
- 段階②以降で50/50生存を維持できているか
- 段階③のスコア上昇を、評価指標変更の影響として読めているか
- 段階④は iter 2 の部分生存（19/50）のあと、③より早く設計を固定していないか

### ARS / OGS / WRS の3パラメータ推移

```bash
python3 analysis/make_parameter_comparison.py
```

生成物:

```text
experiments/outputs/ssos_phase1_phase2_phase3_parameter_trends.svg
```

見るポイント:

- ARSが20.8 kg/day付近を維持できているか
- OGSが42.0 kg/day付近を維持できているか
- WRSの探索範囲が広がっているか
- WRSを下げすぎた失敗境界が見えているか
- 段階④の監査が WRS の下げを止め、1.65 に固定していないか

## 5. 点数内訳の積み上げグラフを生成する

積み上げグラフは2種類作ります。

| 種類 | 分割 | 目的 |
|---|---|---|
| 集約版 | A / B-D / E-F / G | 大きな評価ブロックごとの効き方を見る |
| 詳細版 | A / B / C / D / E / F / G | CostとMass、TCL/Environment/Recoveryを個別に見る |

### 集約版: A / B-D / E-F / G

```bash
python3 analysis/make_score_group_components.py --prefix phase1 --title "段階① 初期: 点数内訳 集約版" --output phase1_score_components_grouped
python3 analysis/make_score_group_components.py --prefix phase2 --title "段階② 記憶あり改善: 点数内訳 集約版" --output phase2_score_components_grouped
python3 analysis/make_score_group_components.py --prefix phase3 --title "段階③ 記憶+評価変更: 点数内訳 集約版" --output phase3_score_components_grouped
python3 analysis/make_score_group_components.py --prefix phase4 --title "段階④ 監査パネル: 点数内訳 集約版" --output phase4_score_components_grouped
```

生成物:

```text
experiments/outputs/phase1_score_components_grouped.csv
experiments/outputs/phase2_score_components_grouped.csv
experiments/outputs/phase3_score_components_grouped.csv
experiments/outputs/phase4_score_components_grouped.csv
experiments/outputs/phase1_score_components_grouped.svg
experiments/outputs/phase2_score_components_grouped.svg
experiments/outputs/phase3_score_components_grouped.svg
experiments/outputs/phase4_score_components_grouped.svg
```

### 詳細版: A / B / C / D / E / F / G

```bash
python3 analysis/make_score_components_split.py --prefix phase1 --title "段階① 初期: 点数内訳 詳細版"
python3 analysis/make_score_components_split.py --prefix phase2 --title "段階② 記憶あり改善: 点数内訳 詳細版"
python3 analysis/make_score_components_split.py --prefix phase3 --title "段階③ 記憶+評価変更: 点数内訳 詳細版"
python3 analysis/make_score_components_split.py --prefix phase4 --title "段階④ 監査パネル: 点数内訳 詳細版"
```

生成物:

```text
experiments/outputs/phase1_score_components_split.csv
experiments/outputs/phase2_score_components_split.csv
experiments/outputs/phase3_score_components_split.csv
experiments/outputs/phase4_score_components_split.csv
experiments/outputs/phase1_score_components_stacked_split.svg
experiments/outputs/phase2_score_components_stacked_split.svg
experiments/outputs/phase3_score_components_stacked_split.svg
experiments/outputs/phase4_score_components_stacked_split.svg
```

見るポイント:

- A Survivalが落ちるiterationはどこか
- B-Dのシステム挙動が安定しているか
- E CostとF Massが段階③で十分に振れているか
- G Ops/Physicsが最終スコア差にどれくらい効いているか

## 6. 4段階サマリを生成する

```bash
python3 analysis/summarize_three_way_inputs.py
```

生成物:

```text
experiments/outputs/ssos_three_way_comparison_summary.json
```

ここには、以下のような比較表向けの値が入ります。

- iteration数
- final replay生存者数
- 50/50生存iteration数
- 0/50生存iteration数
- 最高スコア
- 平均スコア
- 最終スコア
- 完全な設計提案数
- ARS/OGSの巻き戻り回数
- ユニーク設計数
- `chain_memory_compact` の投入状況

## 7. docs配下のコミット済み結果と照合する

生成結果が既存のdocsと一致するか確認します。

Linux / macOS / Git Bash:

```bash
for n in 1 2 3 4; do
  diff outputs/phase${n}_iteration_metrics.csv          ../docs/data/phase${n}_iteration_metrics.csv
  diff outputs/phase${n}_iteration_findings.json        ../docs/data/phase${n}_iteration_findings.json
  diff outputs/phase${n}_score_components_grouped.csv   ../docs/data/phase${n}_score_components_grouped.csv
  diff outputs/phase${n}_score_components_grouped.svg   ../docs/images/results/phase${n}_score_components_grouped.svg
  diff outputs/phase${n}_score_components_split.csv     ../docs/data/phase${n}_score_components_split.csv
  diff outputs/phase${n}_score_components_stacked_split.svg ../docs/images/results/phase${n}_score_components_stacked_split.svg
done

diff outputs/ssos_phase1_phase2_phase3_survival_score_trend.svg ../docs/images/results/ssos_phase1_phase2_phase3_survival_score_trend.svg
diff outputs/ssos_phase1_phase2_phase3_parameter_trends.svg     ../docs/images/results/ssos_phase1_phase2_phase3_parameter_trends.svg
```

Windows PowerShell:

```powershell
1..4 | ForEach-Object {
  Compare-Object (Get-Content "outputs\phase$($_)_iteration_metrics.csv") (Get-Content "..\docs\data\phase$($_)_iteration_metrics.csv")
  Compare-Object (Get-Content "outputs\phase$($_)_iteration_findings.json") (Get-Content "..\docs\data\phase$($_)_iteration_findings.json")
  Compare-Object (Get-Content "outputs\phase$($_)_score_components_grouped.csv") (Get-Content "..\docs\data\phase$($_)_score_components_grouped.csv")
  Compare-Object (Get-Content "outputs\phase$($_)_score_components_grouped.svg") (Get-Content "..\docs\images\results\phase$($_)_score_components_grouped.svg")
  Compare-Object (Get-Content "outputs\phase$($_)_score_components_split.csv") (Get-Content "..\docs\data\phase$($_)_score_components_split.csv")
  Compare-Object (Get-Content "outputs\phase$($_)_score_components_stacked_split.svg") (Get-Content "..\docs\images\results\phase$($_)_score_components_stacked_split.svg")
}

Compare-Object (Get-Content "outputs\ssos_phase1_phase2_phase3_survival_score_trend.svg") (Get-Content "..\docs\images\results\ssos_phase1_phase2_phase3_survival_score_trend.svg")
Compare-Object (Get-Content "outputs\ssos_phase1_phase2_phase3_parameter_trends.svg") (Get-Content "..\docs\images\results\ssos_phase1_phase2_phase3_parameter_trends.svg")
```

差分が出なければ、解析手順はdocsに載っている結果を再現できています。

## 8. 新しいchain結果を解析する場合

新しいchain結果が `src/experiments/results/<run_id>/` にある場合:

```bash
cd experiments
python3 analysis/analyze_ssos_iter.py --root ../src/experiments/results/<run_id> --prefix mychain
python3 analysis/make_score_group_components.py --prefix mychain --title "新規chain: 点数内訳 集約版" --output mychain_score_components_grouped
python3 analysis/make_score_components_split.py --prefix mychain --title "新規chain: 点数内訳 詳細版"
```

生成物:

```text
experiments/outputs/mychain_iteration_metrics.csv
experiments/outputs/mychain_iteration_findings.json
experiments/outputs/mychain_score_components_grouped.svg
experiments/outputs/mychain_score_components_stacked_split.svg
```

3段階比較に新しいchainを加える場合は、`make_comparison_trend.py` と `make_parameter_comparison.py` の `SERIES` に新しいprefixを追加します。

## 9. レポートで確認する観点

### 生存性能

- 最終生存者数が50/50か
- 50/50生存iterationが増えているか
- 0/50や部分生存がどのiterationで起きているか

### 設計変数

- ARS/OGSが理論下限付近を維持できているか
- 過去の良い設計が次iterationで巻き戻っていないか
- WRSを下げすぎた失敗境界が記録されているか
- ユニーク設計数が少なすぎず、探索が局所化していないか

### tool-use / memory

- `load_run_artifacts` が呼ばれているか
- iteration 2以降で `chain_memory_compact` が渡っているか
- 提案がARS/OGS/WRSの3項目をすべて含んでいるか
- `required_evidence_count` と `collected_evidence_count` が一致しているか

### 評価指標

- 段階③④のスコアは段階①/②と単純比較しない（③と④は同じ採点表）
- Cost/Massの点数が適切に振れているか
- 旧評価スコア・新評価スコア・総コスト・総重量を分けて見る
- 段階④の監査 veto が探索を狭めていないか

## 10. Cursorに依頼するときのプロンプト例

```text
このリポジトリの experiments/README.md と docs/data/README.md を読み、
experiments/runs/ にある4つのtar.gzを展開して、解析手順に従って
SSOS ECLSSの4段階比較レポートを再生成してください。

必ず以下を出してください。
- 生存者数・スコアの4段階重ね合わせグラフ
- ARS/OGS/WRSの4段階重ね合わせグラフ
- 点数内訳の集約版: A / B-D / E-F / G
- 点数内訳の詳細版: A / B / C / D / E / F / G
- 段階③④のスコアは評価指標変更後なので、段階①/②と単純比較しないという注意書き
- Cost/Massの点数上昇と、物理的な総コスト・総重量の改善を切り分けた考察

生成結果は experiments/outputs/ に置き、docs/data/ と docs/images/results/ の
コミット済み結果との差分も確認してください。
```

## 11. よくある詰まりどころ

### `chain_summary.json` が見つからない

tar.gzを展開できていないか、`--root` の指定が1階層ずれています。`runs/phase3-rescored/chain_summary.json` のように、`chain_summary.json` が直下にあるディレクトリを `--root` に指定します。

### 段階③のスコアだけ高すぎる

正常です。段階③ではCost/Massの評価式を変えているため、スコアは段階①/②と直接比較できません。比較するなら、生存者数、提案の完全性、ARS/OGS/WRS、総コスト、総重量を見ます。

### 詳細版A-Gのファイルがdocs側にない

`make_score_components_split.py` の生成物がまだdocsにコミットされていない可能性があります。その場合は `experiments/outputs/` に生成された以下をdocs側へ追加します。

```text
docs/data/phaseN_score_components_split.csv
docs/images/results/phaseN_score_components_stacked_split.svg
```

### Windowsで文字化けする

PowerShellで以下を設定してから実行します。

```powershell
$env:PYTHONIOENCODING = 'utf-8'
```


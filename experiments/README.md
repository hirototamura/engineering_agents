# Experiments — raw logs, analysis, and how to get from one to the other

Three fifty-round design→verify chains, archived whole. Every number and every figure in [the experiment record](../docs/en/results.md) / [実験記録](../docs/ja/results.md) is derived from what is in this directory, by the scripts in this directory, and the derivation can be re-run and diffed.

```
experiments/
├── runs/          raw logs, one .tar.gz per chain      <- what the simulator wrote
├── analysis/      the scripts that read them           <- how the numbers were made
└── outputs/       where re-running writes              (gitignored)
                                                        |
../docs/data/      the committed analysed data          <- diff against outputs/
../docs/images/results/  the committed figures
```

`src/experiments/results/` is somewhere else and is not this: that is where *your* local runs land, and it is gitignored. This directory holds the chains the docs cite.

---

## 1. The three chains

| Archive | Rounds | Code | What was different | Result |
| --- | ---: | --- | --- | ---: |
| `runs/phase1-no-chain-memory.tar.gz` | 50 | `b828332` | the loop as first built. No memory between rounds | 34/50 |
| `runs/phase2-chain-memory.tar.gz` | 50 | `c0dcb4f` | `compact_chain_memory.json` carried between rounds | 50/50 |
| `runs/phase3-rescored.tar.gz` | 50 | `46b3f19` | ＋ cost/mass full-marks line moved off the non-surviving baseline; stagnation detector | 50/50 |

11 MB each, ~115 MB extracted. Same world, same fifty-person crew, same non-survivable baseline, `inject_failures: false` throughout.

Each archive carries its own `scenario_config.yaml` and `agents_config.yaml` **per round**, so a chain states the configuration it ran under rather than relying on this table. The differences above are visible there directly:

```bash
tar -xzf runs/phase1-no-chain-memory.tar.gz -C runs/
tar -xzf runs/phase3-rescored.tar.gz -C runs/

# phase 1: full marks on cost/mass sit at the baseline that kills everyone
grep -A4 'footprint:' runs/phase1-no-chain-memory/01/scenario_config.yaml
# phase 3: re-anchored, and the stagnation detector exists
grep -A6 'footprint:' runs/phase3-rescored/01/scenario_config.yaml
```

**Phase 3 scores are not comparable to phases 1–2** — the scoring function changed between them. Comparable across all three: survivors, ARS/OGS/WRS sizing, proposal completeness, physics-gate results.

## 2. What is inside one chain

```
phase3-rescored/
├── 01/ .. 50/                    one round each
│   ├── telemetry.jsonl           every step of the plant: inventories, ledgers, operations
│   ├── messages.jsonl            every agent utterance, its reasoning, and captured thinking
│   ├── events.jsonl              commands, rejections with reasons, crew loss
│   ├── health_metrics.jsonl      safe / warning / critical per step
│   ├── tool_trace.jsonl          every one of the design agent's tool calls and what came back
│   ├── design_decision_state.json  the page the model was shown, and the answer it gave
│   ├── design_proposals.json     the sizing this round handed on
│   ├── applied_proposals.json    the sizing that was actually installed
│   ├── candidate_runs/           the re-simulation of every candidate the model named
│   ├── candidate_rankings.json   how they were ranked, and which criterion decided it
│   ├── evaluation.json           the scorecard, per axis, with points_lost
│   ├── physics_gate.json         the nine telemetry-only mass-balance checks
│   ├── run_integrity.json        whether this run moved its own scoring bar
│   ├── provenance.jsonl          what produced each artifact
│   └── scenario_config.yaml, agents_config.yaml, summary.json
├── baseline-replay/, final-replay/   the paired replay, first design vs last
├── compact_chain_memory.json     the 4 KB note the last round read
├── chain_summary.json            survivors first vs last, verdict
└── chain_final_answer.json       the one design the whole chain answers with
```

Nothing is summarised away. `tool_trace.jsonl` holds the actual arguments and actual return values of all nine tools, and `design_decision_state.json` holds the model's reply verbatim including its reasoning, so a design can be retraced from the telemetry it was based on to the sentence that proposed it.

## 3. Reproduce the analysis

Needs Python 3.11+ and nothing else — the scripts are stdlib only, no numpy, no matplotlib. From this directory:

```bash
cd experiments
for f in runs/*.tar.gz; do tar -xzf "$f" -C runs/; done

python3 analysis/analyze_ssos_iter.py --root runs/phase1-no-chain-memory --prefix phase1
python3 analysis/analyze_ssos_iter.py --root runs/phase2-chain-memory    --prefix phase2
python3 analysis/analyze_ssos_iter.py --root runs/phase3-rescored        --prefix phase3

python3 analysis/make_comparison_trend.py
python3 analysis/make_parameter_comparison.py
python3 analysis/make_score_group_components.py --prefix phase1 --title "段階① 初期: 点数内訳 集約版" --output phase1_score_components_grouped
python3 analysis/make_score_group_components.py --prefix phase2 --title "段階② 記憶あり改善: 点数内訳 集約版" --output phase2_score_components_grouped
python3 analysis/make_score_group_components.py --prefix phase3 --title "段階③ 記憶+評価変更: 点数内訳 集約版" --output phase3_score_components_grouped

# the same score, split into all seven axes -- this is the one that shows cost and mass apart
python3 analysis/make_score_components_split.py --prefix phase1 --title "段階① 初期: 点数内訳 詳細版"
python3 analysis/make_score_components_split.py --prefix phase2 --title "段階② 記憶あり改善: 点数内訳 詳細版"
python3 analysis/make_score_components_split.py --prefix phase3 --title "段階③ 記憶+評価変更: 点数内訳 詳細版"

python3 analysis/summarize_three_way_inputs.py
```

<details>
<summary>Windows PowerShell</summary>

```powershell
cd experiments
Get-ChildItem runs\*.tar.gz | ForEach-Object { tar -xzf $_.FullName -C runs\ }

$env:PYTHONIOENCODING = 'utf-8'   # the scripts print Japanese
python analysis\analyze_ssos_iter.py --root runs/phase1-no-chain-memory --prefix phase1
python analysis\analyze_ssos_iter.py --root runs/phase2-chain-memory    --prefix phase2
python analysis\analyze_ssos_iter.py --root runs/phase3-rescored        --prefix phase3
python analysis\make_comparison_trend.py
python analysis\make_parameter_comparison.py
python analysis\make_score_components_split.py --prefix phase3 --title "段階③ 記憶+評価変更: 点数内訳 詳細版"
python analysis\summarize_three_way_inputs.py
```
</details>

### Then check it against what is committed

**Everything the pipeline writes is committed, and every file is byte-identical.**
Not a list of files to keep in sync — the check is over the whole directory, so a
new artifact that nobody committed fails it:

```bash
for f in outputs/*; do
  b=$(basename "$f")
  for c in "../docs/data/$b" "../docs/images/results/$b"; do
    [ -f "$c" ] && { cmp -s "$f" "$c" && echo "OK   $b" || echo "DIFF $b"; continue 2; }
  done
  echo "MISSING $b — the pipeline writes this and nothing in the repo holds it"
done
```

33 files: 3 phases × (metrics CSV, findings JSON, chain key summary, grouped CSV +
SVG, split CSV + stacked SVG, design-space, design-variables, survival-score) plus
the two cross-phase trends and the three-way comparison summary.

## 4. What each script does

| Script | Reads | Writes |
| --- | --- | --- |
| `analyze_ssos_iter.py` | a chain directory | `<prefix>_iteration_metrics.csv` (50 rows × 54 columns), `<prefix>_iteration_findings.json`, `<prefix>_chain_key_summary.csv`, and three per-chain SVGs |
| `make_comparison_trend.py` | the three metrics CSVs | survivors and score, all three phases on one axis |
| `make_parameter_comparison.py` | the three metrics CSVs | ARS / OGS / WRS across all three phases |
| `make_score_group_components.py` | one metrics CSV | the scorecard in four blocks — survival, system behaviour, footprint, ops/physics |
| `make_score_components_split.py` | one metrics CSV | `<prefix>_score_components_split.csv` and `<prefix>_score_components_stacked_split.svg` — the same score split into all seven axes, cost and mass apart |
| `summarize_three_way_inputs.py` | all three, metrics **and** chain roots | the cross-phase totals the comparison table is built from |

Column meanings: [`docs/data/README.md`](../docs/data/README.md).

## 5. 日本語の手順書

[`ANALYSIS_PROCEDURE.ja.md`](ANALYSIS_PROCEDURE.ja.md) — the same procedure written for somebody
reproducing it on their own machine: what to look for in each figure, what the common
sticking points are, and a ready-made prompt for handing the whole thing to a coding agent.

## 6. Run a new chain

```bash
./scripts/run_design_chain.sh --rounds 50                          # from the repo root
./scripts/run_design_chain.sh --rounds 5 --provider ollama --model qwen3:8b   # a short one
```

Windows: `.\scripts\windows\run_design_chain.ps1 -Rounds 50`.

The design side needs an LLM (`ea doctor` says whether one is reachable). The operators are the deterministic rule base by default, so the difference between two chains is attributable to the design rather than to a different crew improvising.

Phase 3 is what the current code does: `iteration.count: 50`, the four `evaluation.footprint` keys, and `iteration.exploration` are all in the shipped `scenario.yaml`, so `./scripts/run_design_chain.sh` reproduces its conditions. Phases 1 and 2 need their commits checked out — the difference is that `chain_memory.py` did not exist yet, which is not a setting.

The chain will not come out identical. The simulator is deterministic and the LLM is not (temperature 0.45), so a re-run explores a different path through the same world. That is why the whole per-round decision state is archived rather than a summary of it.

Turning your own chain into the same table:

```bash
cd experiments
python3 analysis/analyze_ssos_iter.py --root ../src/experiments/results/<your run id> --prefix mychain
```

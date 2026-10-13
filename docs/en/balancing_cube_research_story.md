# Balancing-cube research story

The bilingual article distills the existing reports into a research question,
retrospective hypotheses, methodology, experiment history, findings, limitations,
and proposed next experiments. It is a derived educational explanation. It does
not modify requirements, canonical records, saved prompts, or past results.

The central finding is that higher exploration scores did not establish a better
confirmed design. Both completed Qwen selections remain provisional. The 20-round
confirmation ran on GPU but has inconclusive CPU/GPU agreement. Physical fidelity
and hardware success remain unverified.

## Build and inspect

From a workspace containing the repositories side by side:

```sh
PYTHONPATH=engineering_agents/src python -m tools.research_story.build \
  --workspace "$PWD" --register
```

The output is under
`engineering_agents/src/experiments/results/balancing-cube-research-story-20261012/`:

- `index.html`: English article.
- `index.ja.html`: Japanese article, translated from the English narrative.
- `evidence.json`: inspectable evidence extract with original values and hashes.

`--register` adds both reading languages to the report collection. It uses native
language/source navigation and the existing screenshot-thumbnail workflow.
The article's charts and replay are self-contained and require no CDN, model,
GPU, or running API. Links to large original evidence assume the workspace or
restored Release artifacts. `--output` can select another destination.

## Read on an iPhone

Double-click `scripts/open_research_on_iphone.command` on the Mac. It exports
`reports/iphone-research/index.html` and `index.ja.html`, then prints phone URLs
for the Mac's private Wi-Fi address. Keep the Terminal window open while reading;
Control-C stops the server. The iPhone and Mac must use the same Wi-Fi network.
This server serves only the two article pages, not the workspace or report
library. For offline reading, transfer either HTML file to the iPhone; all
figures, interactive charts, recorded CPU replay, and evidence values are
embedded. Transfer both files together to use their language switch offline.
The portable source links point to the repositories and campaign Release;
the page can download its embedded evidence JSON without a separate file.

## Evidence and reproducibility

Maintained sources live in `src/tools/research_story/`. `copy.json` contains the
English narrative and its Japanese translation. `template.html` supplies layout,
figures and interactions. `evidence.json` is a frozen extract from the existing
historical analysis and actual Qwen campaign artifacts. `--refresh` re-extracts
those files and records SHA-256 values; it fails if they are absent or inconsistent.
The default build uses the packaged extract, so large archives are not needed to
rebuild the article. No new simulation or LLM generation occurs.

Per-round best scores are computed from **all measured configurations**, including
factorial side cells, rather than only each round's main proposal feedback.
The 3D replay uses saved native CPU position, quaternion and wheel-angle frames
for the matched stress case. It holds the last recorded pose after termination;
it does not invent a continuation or depict hardware footage.

The article separates historical half-step checks from new fixed-timestep trials,
public confirmation conditions from a genuinely unseen holdout, and later
reliability corrections from capabilities present in the archived runs. It makes
no causal claim for memory or the LLM without a controlled ablation.

The research questions are reconstructed after the experiments, not preregistered.
External references identify editorial or methodological inspiration; the project
does not claim to implement MASS training or ENPIRE real-robot code evolution.

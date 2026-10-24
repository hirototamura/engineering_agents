# Balancing-cube research story

The English article and its Japanese translation follow the research question,
requirements, methodology, sequential Qwen trials, MASS-inspired workflow pilot,
human-directed reaction-wheel relocation, unsuccessful attempts, and discussion.
The October 18 revision synthesizes experiments through October 17. It changes
no canonical requirements, saved configurations, prompts, or experiment outcomes.

## Build and read

From the workspace containing both repositories:

```sh
PYTHONPATH=engineering_agents/src python -m tools.research_story.build \
  --workspace "$PWD" --refresh --register
PYTHONPATH=engineering_agents/src python -m tools.research_story.portable \
  --workspace "$PWD"
```

`--refresh` verifies and re-extracts the local sources. Omit it to rebuild from
the frozen packaged extract without large experiment archives. The main output
remains `experiments/balancing_cube/results/balancing-cube-research-story-20261012/` for URL
continuity; its evidence cut and article revision identify the newer content.
`--register` updates both language entries in the existing report collection.

The portable files are `reports/iphone-research/index.html` (English) and
`index.ja.html` (Japanese). Each embeds figures, charts, recorded replay, styles,
scripts, and source data. Transfer both to retain their language switch.
`scripts/open_research_on_iphone.command` serves only those pages to a phone
on the same private Wi-Fi; stop it with Control-C. No server, CDN, model or
GPU is needed to open the files on a compatible desktop browser.

## Score provenance

The article now emphasizes **MJX exploration scores**. `recent.measured_score`
applies the frozen gates and objective directly to each saved `gpu_summary`.
It rejects missing summaries and duplicate/incomplete case matrices. It never
substitutes native MuJoCo summaries when MJX results are absent.

This is a retrospective analysis. Archived search selection used the original
native-summary aggregate. The original score, chosen candidate, and all source
files remain unchanged. For example, the twenty-round run selected round 19,
while its best observed MJX score belongs to round 15. The multi-agent arm's
native-selected candidate is from attempt 6; its MJX maximum is from attempt 9.
A cumulative MJX maximum in the article is not a claim that the running agent
selected that configuration using MJX feedback.

The lower-wheel twelve-case experiment was native MuJoCo only. Its score is
shown separately and is **not** placed on the MJX progress curve. It improved
a known governor-gate failure but reduced its exploration score. The article
omits the implementation-agreement narrative; archived evidence is preserved.

## Experimental boundaries

The paired multi-agent/single-identity pilot attempted ten cycles per arm and
completed eight per arm. Its original dispatch remains inconclusive for ten
complete cycles. Two structured-output failures per arm, unequal actual usage,
and rejected workflow revisions remain visible. Model weights and evaluation
rules stayed fixed. This is an adaptation of MASS workflow search, not a
reproduction of outer-loop training or a statistically replicated ablation.
Both selected designs and the unchanged starting design passed the fresh
12-case MJX audit. There is no fresh-audit pass-rate advantage.

The mounting revision was human-directed. Rotating wheel/rotor bodies move;
fixed motor/stator mass remains in the unchanged lumped frame. Mounts remain
fixed in body coordinates and only corner 000 has been tested. The actual saved
MASS-trial controller is retained; two relinearized alternatives performed
worse. Full lower-model MJX exploration, other corners, calibrated hardware
fidelity, thirty-second hardware holding, and human baseline adoption are not
established.

## Sources and presentation

Maintained files are in `src/tools/research_story/`: `copy.json` contains the
English narrative and Japanese translation; `template.html`,
`recent_sections.html` and `recent.js` implement the article; `build.py` and
`recent.py` extract hash-pinned data. The public article retains research references but omits source-report links,
repository/PR links, hash manifests, and evidence downloads. Chart and replay
data remain embedded so the two language files work without a workspace.
The full extraction and canonical records are unchanged.

The requirements explorer preserves the standards draft separately from the
older revisions actually pinned by the experiments. Requirement wording,
approval, simulation outcome and physical verification remain distinct.
The system graph is a projection of recorded relationships, not a claim of
full SysML semantic compliance. Requirements guidance prioritizes
ISO/IEC/IEEE 29148:2018, applicable NASA guidance, then compatible ASD-STE100;
English normative requirements use `shall`.

Recorded native MuJoCo positions, quaternions, wheel angles and metrics drive
all replays. The renderer respects each configuration's mounting side. It holds
the last recorded frame after termination and invents no continuation. Native
replay is labeled as such and is not the source of the MJX score charts.

The research questions organize existing results retrospectively rather than
claiming preregistration. Future independent repeats, clear output contracts,
and fresh frozen tests are proposed explicitly. HTML generation makes no LLM
calls and launches no new simulation.

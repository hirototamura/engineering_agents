# Balancing-cube workflow study

This is a development simulation study at the Cube system level. It tests whether
bounded multi-agent coordination can improve confirmed designs within a fixed
compute allowance. It does not change requirements or adopt a hardware baseline.
The workflow adapts the fixed-weight inner-loop idea from
[MASS](https://arxiv.org/abs/2610.12176). It does not implement its outer-loop
weight training or reproduce the paper's benchmarks.

## Hypothesis and comparison

The research hypothesis is that separate specialist contexts, explicit evidence
handoffs and critique can produce more robust numerical designs per unit of
computation than a sequential single-designer context.

Both arms use the same Qwen model, initial One-Piece records, previous experiment
history and starting proposal. Each arm has ten attempted proposal cycles. Rejected proposals remain part of that attempt budget; `iterations_completed` counts only cycles that finish EN, PI, R and E. Roles remain
fixed: mechanical specialist, control specialist, critic, coordinator and
workflow optimizer. The multi-agent arm can use blind parallel proposals or
sequential cross-review. The control arm passes its earlier outputs through a
sequential shared context with one designer identity. Both use the same per-step
completion caps and aggregate prompt-token cap. Equal caps do not imply equal
actual token use, elapsed time or numbers of unique simulated configurations.

The incumbent is the best measured exploration configuration. A new proposal
cannot replace it merely because an agent's explanation is persuasive. Identical
compiled inputs can reuse exact prior evaluation records; reports distinguish
proposal cycles from newly measured configurations.

## Engineering and workflow boundaries

- The proposal shall use only the six mechanical variables, registered motor
  family, three LQR weight multipliers and yaw-rate gain.
- The workflow shall preserve the frozen requirement revisions and evaluation
  gates.
- The workflow shall preserve the physics timestep and control period.
- The CPU and GPU paths shall use the same saved controller for a configuration.
- The workflow shall record failed, rejected and incomplete outcomes.
- The workflow shall not mark numerical evidence as physical verification.

The optimizer edits data: routing, specialist order, handoff order and one of
four focus labels. It cannot edit model code, controller code, requirements,
thresholds or model weights. Joint mechanical and controller changes retain the
existing four-cell comparison. New runs do not perform half-step adjudication.

A structured prompt projection retains requirement text, exact revisions,
approval states, numerical criteria, KDP values, units, bounds, parameter origins,
the comparison design and campaign summary. It removes repeated descriptive
metadata and old round arrays. Full inputs remain in hash-pinned artifacts.
The served tokenizer checks every request; the pipeline does not cut JSON text
to fit a context window.

## Pinned source model

The October 17 pilot uses `fixed-dt-mvp-2` for continuity with the preceding twenty-round campaign. That snapshot pins 21 legacy requirement/group records and 37 KDP records. Its requirement source revisions are `trace-20261010-2`, including original Japanese labels and values. The newer English shall drafts remain separate; this run does not retroactively adopt them. Source statement status is not physical verification.

## Evidence and disclosure

Each HTTP request is reconstructed from common data, bounded memory and selected structured earlier outputs. The single-identity control uses this sequential handoff; it is not an unbounded persistent conversation.

Each iteration records specialist drafts, critique, selected settings, compiled
configuration, saved K, case outcomes, backend agreement, workflow revision and
actual prompt/completion usage. It writes numerical evidence to One-Piece and
reads it before the workflow optimizer proposes a change. LLM interpretations
remain hypotheses. Private reasoning text is excluded from the audit files.

Previous public confirmation failures are development memory. The fresh audit
uses predeclared new seeds after all ten attempts in both arms stop and both selections are frozen. Rejected attempts do not become completed simulation cycles. It retains the same
domains, release conditions, gates and saved controllers. Its outcomes are not
provided to the proposers during this study. Once disclosed, these outcomes are
also development evidence for any later study. A separately declared audit of
the common starting design distinguishes a design change from a seed change.

Reports retain the original input digest and an audit digest for the new seed
partition. A later metadata revision can link the exact audit snapshot without
changing the measured JSON or its original record revision.

## Execution and analysis

`tools.run_cube_workflow_pair` uses normal Engineering Agents scenario dispatch.
It makes isolated One-Piece store branches from the same immutable initial
commit set. Only immutable commit objects are shared; indexes, locks, new records
and memory are separate. Neither arm reads the other arm's new results. The
branches merge after both arms finish. A common MJX warmup precedes the timed
arms and is recorded separately.

`tools.finalize_cube_workflow_study` audits the frozen selections and starting reference after both arms stop. It preserves the original dispatch status, including an inconclusive status when fewer than ten cycles finish every phase. It checks the merged store and creates an archive with only new canonical commit objects. Postprocessing completion does not mean that every proposal or numerical check passed.
`tools.workflow_study_report` generates standalone English and Japanese HTML
from the measured files. Charts, recorded CPU replay and structured evidence
are embedded in each language page.

The primary outcomes are confirmation gate failures and native MuJoCo–MJX agreement.
Exploration score, constraint margins, duplicate proposals, actual tokens,
unique configurations and elapsed time are supporting outcomes. One paired
pilot does not establish a causal coordination effect or statistical
significance. Further evidence requires independent repeats and reversed
execution order. Physical fidelity and the thirty-second hardware hold remain
unverified.

## Policy for subsequent studies

The completed pilot paired native MuJoCo and MJX for every measured
configuration. The agreed direction for subsequent larger searches is to
qualify MJX on representative success and failure cases, explore with MJX,
and reserve paired comparisons for finalists, sensitive cases and regression
tests. See [execution policy and implementation status](simulation_backend_policy.md).
This forward policy does not change how the pilot ran or its recorded results.

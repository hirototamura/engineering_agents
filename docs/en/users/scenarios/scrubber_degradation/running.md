# Compare scrubber recovery modes

Prerequisites are the [base installation](../../quickstart.md#prepare-the-checkout) and a fresh destination for each run. No model service is needed for baseline or labeled rules.

```bash
PYTHONPATH=src python -m tools.cli run scrubber_degradation \
  --agents-mode none --steps 50 --run-id scrubber-baseline-01 --dry-run --json
PYTHONPATH=src python -m tools.cli run scrubber_degradation \
  --agents-mode labeled_rule_base --steps 50 --run-id scrubber-rules-01 --dry-run --json
```

Review each plan, then remove `--dry-run --json` to execute. The outputs live under `experiments/eclss/results/`. Keep the same anomaly, coefficients, and horizon when comparing modes. To evaluate LLM agents, configure a reachable service and repeat with `--agents-mode llm` and a new run ID.

Open both summaries and compare peak CO₂, minimum/final power margin, the first threshold crossing, and recovery steps. Inspect telemetry and recovery-command events to establish which operations preceded the change. The [results contract](results.md) explains the bands and row semantics.

Agent runs also write `design_proposals.json`. Treat it as a recommendation for review. There is no supported command in this scenario that consumes it and re-simulates the permanent change. Do not use a viewer's design preview as improvement evidence.

Completion means both runs retained their configurations and observations and you can trace each recovery claim to recorded actions and telemetry. It does not mean this simplified model validates a physical scrubber.

## Read the run as a timeline

| Stage | No agents | Labeled rules | LLM |
| --- | --- | --- | --- |
| Before the configured anomaly | Establish the unassisted trajectory | Observe the same plant | Observe the same plant |
| At anomaly activation | Degradation starts | Diagnose from the recorded observations | Model-dependent diagnosis/discussion |
| Recovery opportunity | No commands | Policy-selected operations | Model-selected permitted operations |
| After the horizon | Baseline summary | Summary and rule recommendation | Summary and generated recommendation |

The configured activation step is stated in [configuration](configuration.md); read actual crossing and recovery times from each summary. Approximate timings in older walkthroughs are not acceptance criteria. Align the two runs by simulation step and compare accepted operations before attributing a trajectory difference to the team.

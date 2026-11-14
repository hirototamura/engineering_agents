# Inspect a run's evidence

Start with the output directory printed by the command. For runs under the default experiment roots:

```bash
PYTHONPATH=src python -m tools.cli results --limit 10
PYTHONPATH=src python -m tools.cli results quickstart-run2
PYTHONPATH=src python -m tools.cli results --track balancing_cube --limit 10
```

`results` reads `summary.json`; it does not rerun evaluation. A chain parent has `chain_summary.json`, so inspect that file directly. If you used a custom output directory, open it directly rather than expecting the default-root listing to find it.

## Follow the evidence in order

1. Confirm the scenario, backend, modes, horizon, requirements, and saved configuration.
2. Identify the design actually consumed. A proposal beside a run often describes the *next* design.
3. Read the scenario's evaluation status and any invalidity, applicability, or inconclusive reasons.
4. Trace important values to telemetry and events, then compare runs under matching conditions.

Use the [artifact reference](../reference/artifacts.md) to locate records. [Scrubber results](../scenarios/scrubber_degradation/results.md), [ECLSS results](../scenarios/ssos_eclss_loop/results.md), and [cube results](../scenarios/balancing_cube/results.md) define their own metrics and limitations.

## Use viewers to inspect, then return to records

The optional ECLSS Streamlit dashboard reads experiment files:

```bash
PYTHONPATH=src python -m streamlit run src/tools/dashboard/app.py
```

ECLSS runs also write an `evaluation.html` and an `evaluation_browser.html`. The browser provides neighboring-run inspection. The [report library](reports.md) gathers HTML evidence across a workspace.

An empty stream can mean no event of that kind occurred; a missing or malformed summary is a failed result read. A partial score is not zero. Multiple telemetry rows at one step can represent pre-operation and `post_ops` states, so do not treat every JSONL line as a new simulation interval.

## Work from a claim back to its inputs

| A report says… | Read next | Check before accepting the claim |
| --- | --- | --- |
| “Recovered” | Telemetry plus accepted operations/events | The scenario's recovery definition and time window |
| “Better score” | Both evaluation records and effective inputs | Same scorecard, units, requirements, and conditions |
| “Applied design” | Consumed proposal or compiled configuration | Proposed values actually reached the simulator |
| “Numerically confirmed” | Independent validation and backend comparison | Complete case matrix, matching saved controller and conditions |
| “Before/After” | The source run and preview label | Whether After is a new simulation or only a proposed graph |

The preserved [scrubber dashboard walkthrough](../scenarios/scrubber_degradation/results.md#read-the-dashboard) illustrates a two-run view, step replay, and an unverified topology preview. The [ECLSS historical example](../scenarios/ssos_eclss_loop/results.md#historical-four-chain-record) demonstrates a scorecard change that must not be read as an equivalent design gain. [Cube evidence](../scenarios/balancing_cube/results.md) separates case success, scalar ranking, and numerical agreement.

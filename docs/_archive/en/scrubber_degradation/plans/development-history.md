# Development history

Historical milestone record. See the [scenario parent](../../../../en/users/scenarios/scrubber_degradation/index.md) for current behavior.

### scrubber_degradation (Mock ECLSS + EPS) — complete

| Area | Contents |
| --- | --- |
| Simulator | `StationSimulator` (`MockEclssSimulator` + `EpsBackend` mock / `ssos_eps`) |
| Scenario | `scrubber_degradation` — 50 steps, anomaly from step 20 |
| Agents | `none` / `labeled_rule_base` / `llm`, homogeneous N engineers |
| Recovery | Fan boost, load shed, EPS boost, temporary bypass |
| Post-run design | `design_proposals.json` (scrubber frozen; no runtime topology change) |
| provenance | Runtime **recovery** (`request_eps_boost`) |
| Dashboard | CO₂ ppm / EPS / topology / 2-run compare |

```text
[ scrubber_degradation — Mock frozen ]
  StationSimulator → ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json (scrubber domain)
  Dashboard (ppm / EPS / topology)
```

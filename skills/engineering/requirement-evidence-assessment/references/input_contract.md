# Input contract

configuration_digest, design_ref, full requirements and evidence with exact revision references, domain, metric, unit, conditions, status and artifact path/SHA-256. Non-synthetic input requires a One-Piece store and a single project_id; synthetic_validation is explicitly labelled.

Input contract version 2 requires each referenced artifact to be a JSON metric
record with `schema: "engineering_metric_evidence/v1"`. It must contain the
same `id`, `requirement_ref`, `design_ref`, `configuration_digest`, `domain`,
`metric`, `unit`, `conditions`, `status` and `value` as the evidence entry. The
runner reads and hashes the artifact; assessment uses the value from that
verified record. A mismatch, missing or unrecognized record stays inconclusive.
See `examples/simulation.json` for the complete record. Legacy telemetry needs
a deterministic adapter to this format before it can support a pass or fail.
The `value` may be null for a failed execution; a completed execution requires a
finite numeric value for numerical assessment.

The hash binds the record's bytes to the assessment; it does not authenticate the
producer or establish that the measurement or simulation represents reality.
Artifact provenance and physical validation remain separate responsibilities.
Boolean and string criteria are currently inconclusive; numeric criteria use
finite numbers and supported comparison operators.

Keep measured, assumed, derived and synthetic inputs distinct. Supply source references and the operating point/model scope when available. An output inherits the input model limitations; missing data are not inferred as measured values.

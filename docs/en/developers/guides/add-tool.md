# Add an agent tool

Add a tool when a recurring engineering question needs a deterministic, inspectable operation. First decide whether it reads evidence, computes a derived quantity, proposes a design, or executes a candidate. That distinction controls side effects, provenance, and what the result can establish.

## Extend the owning toolkit

For SSOS, update [design_tools.py](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/ssos_eclss_loop/design_tools.py):

1. Implement the operation with explicit input units, bounds, missing-data behavior, and a compact JSON-serializable result.
2. Register its handler and `ToolSpec` so `catalog()`, `tool_names()`, and `call()` agree. Expose enough argument meaning for the designer to use it correctly.
3. If use of the tool satisfies an evidence obligation, add the evidence label deliberately. Only a successful designer call should receive that credit. Report assembly can call with `record_evidence=False` and must not make the ledger claim the agent performed a comparison.
4. Connect trace and prompt handling in `scenario/agents/ssos_tool_use_design.py` only where needed. Preserve budgets, repair behavior, and provenance.

Cube tools and specialist handoffs belong to its adapter/workflow. An analysis script in `tools/` is not automatically available to an agent. Avoid introducing a project-wide registry until a concrete cross-scenario requirement justifies it.

## Specify the operation before exposing it

| Tool kind | Successful result must distinguish | Typical rejected input | Required test |
| --- | --- | --- | --- |
| Evidence read | Found, missing, malformed, and intentionally omitted | Unknown artifact/source | Missing data remains missing |
| Derived calculation | Input measurements, units, method, and computed output | Non-finite or incompatible quantities | Independent expected arithmetic |
| Proposal construction | Suggested fields versus installed fields | Unsupported variable | No state/evidence mutation |
| Candidate execution | Applied input, run identity, measured outcome | Invalid design or exhausted budget | Failure retains inspectable evidence |
| Comparison | Comparable conditions and deterministic ranking | Changed requirements or missing outcome | Invalid high-score candidate cannot win |

For a concrete current example, the SSOS [tool catalog and fixed procedure](../scenarios/ssos_eclss_loop/implementation.md#design-toolkit) show the nine operations and which calls Python schedules. Adding a catalog entry does not make the LLM an autonomous tool scheduler.

## Keep claims bounded

A sizing tool does not simulate. A simulation tool does not revise verification requirements. A plot must return useful textual measurements as well as an image path. Candidate execution must disable nested design, isolate outputs, preserve applied configuration, and use the same evaluator as ordinary runs.

Test valid inputs, unknown names, malformed arguments, handler failure, non-finite or absent evidence, and deterministic results in `tests/scenario/test_ssos_design_tools.py` or the corresponding scenario suite. For mutating tools, verify admission and retained evidence after rejection or interruption. Check that failed calls receive no evidence credit, and that report housekeeping does not gain agent credit. Update [tools and memory](../tools-memory.md) if the responsibility boundary changes.

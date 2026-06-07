"""Streamlit dashboard for scrubber_degradation run outputs."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import matplotlib.pyplot as plt
import streamlit as st

RESULTS_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "results"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _list_runs() -> List[Path]:
    if not RESULTS_ROOT.exists():
        return []
    runs = []
    for entry in RESULTS_ROOT.iterdir():
        if entry.is_dir() and (entry / "summary.json").exists():
            runs.append(entry)
    return sorted(runs, key=lambda p: p.name)


def _select_rows_at_step(rows: List[Dict[str, Any]], step: int) -> List[Dict[str, Any]]:
    return [r for r in rows if int(r.get("step", -1)) == step]


_BCDU_MODE_Y = {"idle": 0, "charging": 1, "discharging": 2, "fault": 3, "safe": 4}


def _line_plot(
    telemetry_rows: List[Dict[str, Any]],
    eps_rows: List[Dict[str, Any]],
    current_step: int,
) -> None:
    if not telemetry_rows:
        st.info("No telemetry data found.")
        return

    steps = [int(r["step"]) for r in telemetry_rows]
    co2 = [float(r["co2_ppm"]) for r in telemetry_rows]
    power = [float(r["power_margin_w"]) for r in telemetry_rows]
    eps_support = [float(r.get("eps_support_w", 0.0)) for r in telemetry_rows]

    nrows = 5 if eps_rows else 3
    fig, axes = plt.subplots(nrows, 1, figsize=(10, 3 * nrows), sharex=True)
    if nrows == 3:
        axes = list(axes)

    axes[0].plot(steps, co2, color="#1f77b4", linewidth=2)
    axes[0].axhline(1000.0, color="#ff7f0e", linestyle="--", linewidth=1)
    axes[0].axvline(current_step, color="#d62728", linestyle=":", linewidth=1)
    axes[0].set_ylabel("CO2 (ppm)")
    axes[0].set_title("CO2 trajectory")
    axes[0].grid(alpha=0.2)

    axes[1].plot(steps, power, color="#2ca02c", linewidth=2)
    axes[1].axhline(0.0, color="#ff7f0e", linestyle="--", linewidth=1)
    axes[1].axvline(current_step, color="#d62728", linestyle=":", linewidth=1)
    axes[1].set_ylabel("Power margin (W)")
    axes[1].set_title("ECLSS net power margin (loads − generation budget; EPS boost added per step)")
    axes[1].grid(alpha=0.2)

    axes[2].plot(steps, eps_support, color="#9467bd", linewidth=2)
    axes[2].axvline(current_step, color="#d62728", linestyle=":", linewidth=1)
    axes[2].set_ylabel("EPS support (W)")
    axes[2].set_title("EPS support (ECLSS telemetry)")
    axes[2].grid(alpha=0.2)

    if eps_rows:
        eps_steps = [int(r["step"]) for r in eps_rows]
        solar_v = [float(r.get("solar_voltage_v") or 0.0) for r in eps_rows]
        bcdu_y = [_BCDU_MODE_Y.get(str(r.get("bcdu_mode", "idle")), 0) for r in eps_rows]
        bcdu_support = [float(r.get("support_w", 0.0)) for r in eps_rows]

        axes[3].plot(eps_steps, solar_v, color="#e377c2", linewidth=2)
        axes[3].axvline(current_step, color="#d62728", linestyle=":", linewidth=1)
        axes[3].set_ylabel("Solar V")
        axes[3].set_title("SARJ solar voltage (beta fixed in mock)")
        axes[3].grid(alpha=0.2)

        ax_mode = axes[4]
        ax_support = ax_mode.twinx()
        ax_mode.plot(eps_steps, bcdu_y, color="#17becf", linewidth=2, drawstyle="steps-post", label="BCDU mode")
        ax_support.plot(
            eps_steps,
            bcdu_support,
            color="#9467bd",
            linewidth=1.5,
            linestyle="--",
            alpha=0.9,
            label="Support W",
        )
        ax_mode.axvline(current_step, color="#d62728", linestyle=":", linewidth=1)
        ax_mode.set_yticks(list(_BCDU_MODE_Y.values()))
        ax_mode.set_yticklabels(list(_BCDU_MODE_Y.keys()))
        ax_mode.set_ylabel("BCDU mode")
        ax_support.set_ylabel("Support (W)")
        max_support = max(bcdu_support) if bcdu_support else 1.0
        ax_support.set_ylim(0.0, max(max_support * 1.15, 10.0))
        ax_mode.set_title("BCDU mode (left) + discharge support W (right, dashed)")
        ax_mode.set_xlabel("Step")
        ax_mode.grid(alpha=0.2)
        lines = ax_mode.get_lines() + ax_support.get_lines()
        ax_mode.legend(lines, [line.get_label() for line in lines], loc="upper right", fontsize=8)
    else:
        axes[2].set_xlabel("Step")

    st.pyplot(fig, use_container_width=True)


def _render_step_tables(
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    provenance: List[Dict[str, Any]],
    current_step: int,
) -> None:
    step_messages = _select_rows_at_step(messages, current_step)
    step_events = _select_rows_at_step(events, current_step)
    step_provenance = _select_rows_at_step(provenance, current_step)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Messages")
        if step_messages:
            st.dataframe(step_messages, use_container_width=True, hide_index=True)
        else:
            st.caption("No messages at this step.")
    with col2:
        st.subheader("Events")
        if step_events:
            st.dataframe(step_events, use_container_width=True, hide_index=True)
        else:
            st.caption("No events at this step.")
    with col3:
        st.subheader("Provenance")
        if step_provenance:
            st.dataframe(step_provenance, use_container_width=True, hide_index=True)
        else:
            st.caption("No provenance records at this step.")


_NODE_ANCHORS: Dict[str, Tuple[float, float]] = {
    "cabin": (0.0, 0.55),
    "manifold": (0.45, 0.55),
    "scrubber": (0.9, 0.55),
    "power_bus": (0.45, 0.05),
}

_EDGE_COLORS = {
    "flow": "#1f77b4",
    "bypass": "#ff7f0e",
    "power": "#9467bd",
    "monitor": "#e377c2",
}

_NODE_COLORS = {
    "volume": "#8c564b",
    "manifold": "#17becf",
    "scrubber": "#2ca02c",
    "electrical": "#d62728",
    "threshold_monitor": "#bcbd22",
    "monitor": "#bcbd22",
    "synthetic": "#9aa5b1",
    "node": "#6c757d",
}

_BASELINE_EDGE_KEYS = frozenset(
    {
        ("cabin", "manifold", "flow"),
        ("manifold", "scrubber", "flow"),
        ("scrubber", "cabin", "flow"),
        ("power_bus", "scrubber", "power"),
    }
)
_DESIGN_EDGE_COLOR = "#c0392b"


def _edge_key(edge: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("kind", "flow")),
    )


def _prepare_topology_for_display(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    *,
    proposed_edge_keys: Optional[Set[Tuple[str, str, str]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Set[Tuple[str, str, str]]]:
    """Deduplicate edges, synthesize missing endpoints, tag proposal deltas."""
    node_by_id: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        if node_id:
            node_by_id[node_id] = dict(node)

    seen_edges: Set[Tuple[str, str, str]] = set()
    deduped_edges: List[Dict[str, Any]] = []
    for edge in edges:
        key = _edge_key(edge)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        deduped_edges.append(edge)
        for endpoint in (key[0], key[1]):
            if endpoint and endpoint not in node_by_id:
                node_by_id[endpoint] = {
                    "id": endpoint,
                    "name": endpoint,
                    "kind": "synthetic",
                    "synthetic": True,
                }

    if proposed_edge_keys is None:
        proposed_edge_keys = {key for key in seen_edges if key not in _BASELINE_EDGE_KEYS}
    display_nodes = list(node_by_id.values())
    return display_nodes, deduped_edges, proposed_edge_keys


def _layout_node_positions(nodes: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    positions: Dict[str, Tuple[float, float]] = {}
    extras: List[str] = []
    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        if node_id in _NODE_ANCHORS:
            positions[node_id] = _NODE_ANCHORS[node_id]
        else:
            extras.append(node_id)
    for index, node_id in enumerate(extras):
        angle = (2.0 * math.pi * index) / max(len(extras), 1)
        positions[node_id] = (0.45 + 0.32 * math.cos(angle), 0.3 + 0.22 * math.sin(angle))
    return positions


_LABEL_BBOX = {
    "boxstyle": "round,pad=0.25",
    "facecolor": "white",
    "edgecolor": "#b0b8c4",
    "linewidth": 0.8,
    "alpha": 0.95,
}


def _draw_topology_graph(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    proposed_edge_keys: Set[Tuple[str, str, str]],
    *,
    proposed_node_ids: Optional[Set[str]] = None,
    title: str = "ECLSS topology",
) -> None:
    if not nodes:
        st.info("No topology nodes to display.")
        return

    if proposed_node_ids is None:
        proposed_node_ids = set()

    positions = _layout_node_positions(nodes)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor("#eef1f5")
    ax.set_facecolor("#eef1f5")

    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source not in positions or target not in positions:
            continue
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        kind = str(edge.get("kind", "flow"))
        key = _edge_key(edge)
        is_proposed = key in proposed_edge_keys
        color = _DESIGN_EDGE_COLOR if is_proposed else _EDGE_COLORS.get(kind, "#7f7f7f")
        linestyle = "dashed" if is_proposed else "solid"
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={
                "arrowstyle": "->",
                "color": color,
                "lw": 2.5 if is_proposed else 2.0,
                "linestyle": linestyle,
                "shrinkA": 14,
                "shrinkB": 14,
            },
            zorder=1 if is_proposed else 2,
        )
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        edge_label = f"{kind}*" if is_proposed else kind
        ax.text(
            mid_x,
            mid_y,
            edge_label,
            fontsize=8,
            color="#1f2933",
            ha="center",
            va="center",
            bbox=_LABEL_BBOX,
            zorder=3,
        )

    for node in nodes:
        node_id = str(node.get("id", ""))
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        kind = str(node.get("kind", "volume"))
        is_proposed_node = node_id in proposed_node_ids
        is_synthetic = bool(node.get("synthetic"))
        if is_synthetic:
            color = _NODE_COLORS["synthetic"]
            size = 500
        else:
            color = _NODE_COLORS.get(kind, "#7f7f7f")
            size = 700 if is_proposed_node else 900
        edgecolor = _DESIGN_EDGE_COLOR if is_proposed_node else "#2d3436"
        marker = "s" if is_synthetic else "o"
        ax.scatter(
            [x],
            [y],
            s=size,
            c=color,
            marker=marker,
            edgecolors=edgecolor,
            linewidths=2.0 if is_proposed_node else 1.5,
            zorder=4,
        )
        label = str(node.get("name", node_id))
        suffix = " [proposed]" if is_proposed_node and not is_synthetic else ""
        if is_synthetic:
            suffix = " [ref]"
        ax.text(
            x,
            y,
            f"{label}\n({node_id}){suffix}",
            ha="center",
            va="center",
            fontsize=8,
            color="#1f2933",
            bbox=_LABEL_BBOX,
            zorder=5,
        )

    ax.set_xlim(-0.15, 1.05)
    ax.set_ylim(-0.05, 0.75)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, color="#1f2933")
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


def _run_end_design_state(
    design_state_rows: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not design_state_rows:
        return {}, {}
    final_row = design_state_rows[-1]
    return dict(final_row.get("topology", {})), dict(final_row.get("parameters", {}))


def _topology_edge_keys(topology: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    return {_edge_key(edge) for edge in topology.get("edges", [])}


def _topology_node_ids(topology: Dict[str, Any]) -> Set[str]:
    return {str(node.get("id", "")) for node in topology.get("nodes", []) if node.get("id")}


def _apply_proposal_changes(
    baseline_topology: Dict[str, Any],
    baseline_parameters: Dict[str, float],
    changes: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    topology = copy.deepcopy(baseline_topology)
    parameters = dict(baseline_parameters)
    nodes = list(topology.get("nodes", []))
    edges = list(topology.get("edges", []))

    for change in changes:
        change_kind = str(change.get("change_kind", ""))
        payload = change.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if change_kind == "add_node":
            node_id = str(payload.get("id", "")).strip()
            if node_id and node_id not in {str(n.get("id", "")) for n in nodes}:
                nodes.append(
                    {
                        "id": node_id,
                        "name": payload.get("name", node_id),
                        "kind": payload.get("kind", "volume"),
                    }
                )
        elif change_kind == "add_edge":
            source = payload.get("node_a")
            target = payload.get("node_b")
            kind = payload.get("kind", "bypass")
            key = (str(source), str(target), str(kind))
            if source and target and key not in {_edge_key(edge) for edge in edges}:
                edges.append({"source": source, "target": target, "kind": kind})
        elif change_kind == "set_parameter":
            key = str(payload.get("key", "")).strip()
            if key:
                try:
                    parameters[key] = float(payload.get("value"))
                except (TypeError, ValueError):
                    continue

    return {"nodes": nodes, "edges": edges}, parameters


def _render_topology_panel(
    *,
    title: str,
    topology: Dict[str, Any],
    proposed_edge_keys: Set[Tuple[str, str, str]],
    proposed_node_ids: Set[str],
) -> None:
    raw_nodes = topology.get("nodes", [])
    raw_edges = topology.get("edges", [])
    nodes, edges, _ = _prepare_topology_for_display(
        raw_nodes,
        raw_edges,
        proposed_edge_keys=proposed_edge_keys,
    )
    _draw_topology_graph(
        nodes,
        edges,
        proposed_edge_keys,
        proposed_node_ids=proposed_node_ids,
        title=title,
    )
    table_edges = [
        {**edge, "proposed": _edge_key(edge) in proposed_edge_keys}
        for edge in edges
    ]
    table_nodes = [
        {
            **node,
            "proposed": str(node.get("id", "")) in proposed_node_ids,
            "synthetic": bool(node.get("synthetic")),
        }
        for node in nodes
    ]
    st.markdown("**Nodes**")
    st.dataframe(table_nodes, use_container_width=True, hide_index=True)
    st.markdown("**Edges**")
    st.dataframe(table_edges, use_container_width=True, hide_index=True)


def _render_topology_proposal_comparison(
    run_dir: Path,
    design_state_rows: List[Dict[str, Any]],
) -> None:
    st.subheader("Design topology — proposal comparison")
    proposal = _read_json(run_dir / "design_proposals.json")
    if not proposal:
        st.info("No design_proposals.json for this run.")
        return

    run_end_topology, run_end_parameters = _run_end_design_state(design_state_rows)
    baseline_topology = proposal.get("baseline_topology") or run_end_topology
    if not baseline_topology:
        st.warning("Proposal has no baseline topology and design_state.jsonl is empty.")
        return

    changes = proposal.get("changes", [])
    if not isinstance(changes, list):
        changes = []
    proposed_topology, proposed_parameters = _apply_proposal_changes(
        baseline_topology,
        run_end_parameters,
        changes,
    )

    before_edge_keys = _topology_edge_keys(baseline_topology)
    after_edge_keys = _topology_edge_keys(proposed_topology)
    before_node_ids = _topology_node_ids(baseline_topology)
    after_node_ids = _topology_node_ids(proposed_topology)
    delta_edge_keys = after_edge_keys - before_edge_keys
    delta_node_ids = after_node_ids - before_node_ids

    st.caption(
        "Compare run-end topology (before proposals) with the topology if design_engineer "
        "changes were applied. Proposals are not applied during simulation."
    )
    if proposal.get("message"):
        st.markdown(f"**Proposal:** {proposal['message']}")
    if proposal.get("reasoning"):
        st.caption(proposal["reasoning"])

    meta_cols = st.columns(3)
    with meta_cols[0]:
        st.metric("Proposed changes", len(changes))
    with meta_cols[1]:
        st.metric("New edges", len(delta_edge_keys))
    with meta_cols[2]:
        st.metric("New nodes", len(delta_node_ids))

    if changes:
        st.markdown("**Proposed change list**")
        st.dataframe(changes, use_container_width=True, hide_index=True)

    graph_cols = st.columns(2)
    with graph_cols[0]:
        st.markdown("**Before (run-end baseline)**")
        _render_topology_panel(
            title="Run-end topology",
            topology=baseline_topology,
            proposed_edge_keys=set(),
            proposed_node_ids=set(),
        )
    with graph_cols[1]:
        st.markdown("**After (if proposals applied)**")
        _render_topology_panel(
            title="Proposed topology",
            topology=proposed_topology,
            proposed_edge_keys=delta_edge_keys,
            proposed_node_ids=delta_node_ids,
        )

    baseline_legend = ", ".join(f"{kind}={color}" for kind, color in _EDGE_COLORS.items())
    st.caption(
        f"Baseline edges: {baseline_legend}. "
        f"Proposed additions: dashed {_DESIGN_EDGE_COLOR} (*)."
    )

    parameter_keys = sorted(
        set(run_end_parameters.keys())
        | set(proposed_parameters.keys())
        | {
            str((change.get("payload") or {}).get("key", ""))
            for change in changes
            if change.get("change_kind") == "set_parameter"
        }
        - {""}
    )
    if parameter_keys:
        param_rows: List[Dict[str, Any]] = []
        for key in parameter_keys:
            before_value = run_end_parameters.get(key)
            after_value = proposed_parameters.get(key)
            delta = None
            if isinstance(before_value, (int, float)) and isinstance(after_value, (int, float)):
                delta = round(after_value - before_value, 6)
            param_rows.append(
                {
                    "parameter": key,
                    "before": before_value,
                    "after": after_value,
                    "delta": delta,
                    "proposed": before_value != after_value,
                }
            )
        st.markdown("**Design parameters (before vs proposed)**")
        st.dataframe(param_rows, use_container_width=True, hide_index=True)


def _render_summary(summary: Dict[str, Any]) -> None:
    st.subheader("Run summary")
    if not summary:
        st.warning("summary.json not found.")
        return
    st.json(summary, expanded=False)


def _render_health_card(
    telemetry_rows: List[Dict[str, Any]],
    health_rows: List[Dict[str, Any]],
    eps_rows: List[Dict[str, Any]],
    current_step: int,
) -> None:
    current_telemetry = next((r for r in telemetry_rows if int(r["step"]) == current_step), None)
    current_health = next((r for r in health_rows if int(r["step"]) == current_step), None)
    current_eps = next((r for r in eps_rows if int(r["step"]) == current_step), None)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Step", current_step)
    with col2:
        st.metric("CO2 ppm", f"{(current_telemetry or {}).get('co2_ppm', '-')}")
    with col3:
        st.metric("Power margin W", f"{(current_telemetry or {}).get('power_margin_w', '-')}")
    with col4:
        st.metric("Overall health", (current_health or {}).get("overall", "-"))
    with col5:
        st.metric("EPS support W", f"{(current_telemetry or {}).get('eps_support_w', 0.0)}")
    with col6:
        st.metric("BCDU mode", (current_eps or {}).get("bcdu_mode", "-"))


def _extract_recovery_commands(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for event in events:
        if event.get("kind") != "/eclss/events/recovery_applied":
            continue
        command = event.get("command") or {}
        rows.append(
            {
                "step": event.get("step"),
                "kind": command.get("kind"),
                "value": command.get("value"),
                "issued_by": command.get("issued_by"),
                "message": event.get("message"),
            }
        )
    return rows


def _render_power_recovery_comparison(
    primary_name: str,
    primary_events: List[Dict[str, Any]],
    primary_summary: Dict[str, Any],
    compare_name: str,
    compare_events: List[Dict[str, Any]],
    compare_summary: Dict[str, Any],
) -> None:
    st.markdown("**Power recovery commands (rule vs LLM)**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "EPS boost step",
            f"{primary_summary.get('eps_boost_applied_step', '-')}"
            f" / {compare_summary.get('eps_boost_applied_step', '-')}",
        )
    with col2:
        st.metric(
            "Min power margin W",
            f"{primary_summary.get('min_power_margin_w', '-')}"
            f" / {compare_summary.get('min_power_margin_w', '-')}",
        )
    with col3:
        st.metric(
            "Power recovered step",
            f"{primary_summary.get('power_recovered_above_critical_step', '-')}"
            f" / {compare_summary.get('power_recovered_above_critical_step', '-')}",
        )
    with col4:
        p_eps = len([r for r in _extract_recovery_commands(primary_events) if r["kind"] == "request_eps_boost"])
        c_eps = len([r for r in _extract_recovery_commands(compare_events) if r["kind"] == "request_eps_boost"])
        st.metric("EPS boost commands", f"{p_eps} / {c_eps}")

    rec_cols = st.columns(2)
    with rec_cols[0]:
        st.caption(f"`{primary_name}` recovery events")
        st.dataframe(_extract_recovery_commands(primary_events), use_container_width=True, hide_index=True)
    with rec_cols[1]:
        st.caption(f"`{compare_name}` recovery events")
        st.dataframe(_extract_recovery_commands(compare_events), use_container_width=True, hide_index=True)


def _extract_final_parameters(design_state_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not design_state_rows:
        return {}
    return dict(design_state_rows[-1].get("parameters", {}))


def _render_run_comparison(
    primary_name: str,
    primary_summary: Dict[str, Any],
    primary_design_state: List[Dict[str, Any]],
    primary_provenance: List[Dict[str, Any]],
    compare_name: str,
    compare_summary: Dict[str, Any],
    compare_design_state: List[Dict[str, Any]],
    compare_provenance: List[Dict[str, Any]],
    primary_events: List[Dict[str, Any]],
    compare_events: List[Dict[str, Any]],
) -> None:
    st.subheader("Run comparison")
    st.caption(f"Primary: `{primary_name}` vs Compare: `{compare_name}`")

    _render_power_recovery_comparison(
        primary_name,
        primary_events,
        primary_summary,
        compare_name,
        compare_events,
        compare_summary,
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Design changes",
            f"{primary_summary.get('design_change_count', 0)} / {compare_summary.get('design_change_count', 0)}",
        )
    with col2:
        st.metric(
            "Provenance records",
            f"{len(primary_provenance)} / {len(compare_provenance)}",
        )
    with col3:
        st.metric(
            "Final CO2 ppm",
            f"{primary_summary.get('final_co2_ppm', '-')}/{compare_summary.get('final_co2_ppm', '-')}",
        )
    with col4:
        st.metric(
            "Final power margin W",
            f"{primary_summary.get('final_power_margin_w', '-')}/{compare_summary.get('final_power_margin_w', '-')}",
        )

    primary_params = _extract_final_parameters(primary_design_state)
    compare_params = _extract_final_parameters(compare_design_state)
    keys = sorted(set(primary_params.keys()) | set(compare_params.keys()))
    diff_rows: List[Dict[str, Any]] = []
    for key in keys:
        a = primary_params.get(key)
        b = compare_params.get(key)
        delta = None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            delta = round(a - b, 6)
        diff_rows.append(
            {
                "parameter": key,
                f"{primary_name}": a,
                f"{compare_name}": b,
                "delta_primary_minus_compare": delta,
            }
        )
    st.markdown("**Final design parameters diff**")
    st.dataframe(diff_rows, use_container_width=True, hide_index=True)

    prov_cols = st.columns(2)
    with prov_cols[0]:
        st.markdown(f"**{primary_name} provenance**")
        st.dataframe(primary_provenance, use_container_width=True, hide_index=True)
    with prov_cols[1]:
        st.markdown(f"**{compare_name} provenance**")
        st.dataframe(compare_provenance, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="ECLSS Day6 Dashboard", layout="wide")
    st.title("ECLSS Resilience Dashboard")

    runs = _list_runs()
    if not runs:
        st.error(f"No run outputs found under {RESULTS_ROOT}")
        return

    run_map = {run.name: run for run in runs}
    run_names = list(run_map.keys())
    selected_run_name = st.sidebar.selectbox("Run", options=run_names, index=len(run_names) - 1)
    run_dir = run_map[selected_run_name]

    compare_enabled = st.sidebar.checkbox("Compare with another run", value=False)
    compare_run_name = None
    compare_run_dir = None
    if compare_enabled:
        compare_candidates = [name for name in run_names if name != selected_run_name]
        if compare_candidates:
            compare_run_name = st.sidebar.selectbox("Compare run", options=compare_candidates, index=0)
            compare_run_dir = run_map[compare_run_name]

    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    eps_telemetry = _read_jsonl(run_dir / "eps_telemetry.jsonl")
    health = _read_jsonl(run_dir / "health_metrics.jsonl")
    messages = _read_jsonl(run_dir / "messages.jsonl")
    events = _read_jsonl(run_dir / "events.jsonl")
    provenance = _read_jsonl(run_dir / "provenance.jsonl")
    design_state = _read_jsonl(run_dir / "design_state.jsonl")
    summary = _read_json(run_dir / "summary.json")

    max_step = max((int(r["step"]) for r in telemetry), default=1)
    current_step = st.sidebar.slider("Step", min_value=1, max_value=max_step, value=max_step)

    st.caption(f"Run directory: `{run_dir}`")
    _render_health_card(telemetry, health, eps_telemetry, current_step)
    _line_plot(telemetry, eps_telemetry, current_step)
    _render_topology_proposal_comparison(run_dir, design_state)
    _render_step_tables(messages, events, provenance, current_step)
    _render_summary(summary)

    if compare_run_name and compare_run_dir:
        compare_summary = _read_json(compare_run_dir / "summary.json")
        compare_design_state = _read_jsonl(compare_run_dir / "design_state.jsonl")
        compare_provenance = _read_jsonl(compare_run_dir / "provenance.jsonl")
        compare_events = _read_jsonl(compare_run_dir / "events.jsonl")
        _render_run_comparison(
            primary_name=selected_run_name,
            primary_summary=summary,
            primary_design_state=design_state,
            primary_provenance=provenance,
            compare_name=compare_run_name,
            compare_summary=compare_summary,
            compare_design_state=compare_design_state,
            compare_provenance=compare_provenance,
            primary_events=events,
            compare_events=compare_events,
        )


if __name__ == "__main__":
    main()

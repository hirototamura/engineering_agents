from environment.eclss_ops.design_state import DesignStateManager


def test_apply_dict_change_add_node_and_edge():
    manager = DesignStateManager()
    manager.apply_dict_change(
        "add_node",
        {"id": "aux_scrubber", "name": "Aux Scrubber", "kind": "scrubber"},
    )
    manager.apply_dict_change(
        "add_edge",
        {"node_a": "manifold", "node_b": "aux_scrubber", "kind": "flow"},
    )

    state = manager.snapshot()
    node_ids = {node.id for node in state.topology.nodes}
    assert "aux_scrubber" in node_ids
    assert any(
        edge.source == "manifold" and edge.target == "aux_scrubber"
        for edge in state.topology.edges
    )

from environment.eclss_ops.design_state import DesignStateManager
from environment.protocol import DesignChange, DesignChangeKind


def test_apply_change_add_node_and_edge():
    manager = DesignStateManager()
    manager.apply_change(
        DesignChange(
            kind=DesignChangeKind.ADD_NODE,
            payload={"id": "aux_scrubber", "name": "Aux Scrubber", "kind": "scrubber"},
            proposed_by="design_engineer",
        )
    )
    manager.apply_change(
        DesignChange(
            kind=DesignChangeKind.ADD_EDGE,
            payload={"node_a": "manifold", "node_b": "aux_scrubber", "kind": "flow"},
            proposed_by="design_engineer",
        )
    )

    state = manager.snapshot()
    node_ids = {node.id for node in state.topology.nodes}
    assert "aux_scrubber" in node_ids
    assert any(
        edge.source == "manifold" and edge.target == "aux_scrubber"
        for edge in state.topology.edges
    )

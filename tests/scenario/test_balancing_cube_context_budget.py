"""High-degree historical graphs must not consume the proposer's context."""
from scenario.balancing_cube.design import digest
from scenario.balancing_cube.loop import _compact_agent_context


def test_high_degree_links_have_a_bounded_projection_and_full_source_digest():
    links = [{"type": "constrain", "target": {"id": f"case-{i}", "revision": "1"}}
             for i in range(2150)]
    context = {"records": [{"id": "numeric-spec", "revision": "1", "kind": "specification",
                             "links": links, "data": {"name": "Fixed numerical gates"}}]}
    result = _compact_agent_context(context, {"model": {}})
    row = result["records"][0]
    assert row["links"] == links[:16]
    assert row["link_projection"] == {"total": 2150, "shown": 16,
        "all_links_digest": digest(links), "full_source": "ssot-context.json"}
    assert context["records"][0]["links"] == links

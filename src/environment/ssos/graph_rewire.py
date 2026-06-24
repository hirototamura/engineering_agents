"""Apply ssos_graph.rewires manifests to ROS topic/service/action names."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional


def build_topic_remap(rewires: Optional[Iterable[Mapping[str, Any]]]) -> Dict[str, str]:
    """Build public→backend remap table from graph_rewire payloads."""
    remap: Dict[str, str] = {}
    if not rewires:
        return remap
    for entry in rewires:
        if not isinstance(entry, dict):
            continue
        public = str(entry.get("public", "")).strip()
        backend = str(entry.get("backend", "")).strip()
        if public and backend:
            remap[public] = backend
    return remap


def remap_name(name: str, remap: Mapping[str, str]) -> str:
    """Map a public ROS graph name to its backend alias when configured."""
    if not remap:
        return name
    if name in remap:
        return remap[name]
    if name.startswith("/"):
        alt = name.lstrip("/")
        if alt in remap:
            return remap[alt]
    else:
        alt = f"/{name}"
        if alt in remap:
            return remap[alt]
    return name

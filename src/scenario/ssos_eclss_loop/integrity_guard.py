"""Did this run move the bar it is measured against? (spec §11)

A design agent that may edit the scenario has a cheaper route to a good score
than designing anything: loosen the thresholds, start with a fuller oxygen
tank, carry fewer people. The physics would be unchanged and the scorecard
would improve. This guard compares the config a run actually used against the
pristine config on disk and classifies every difference.

Three classes, following the spec:

``scoring_bar``
    What the run is judged by. A run that changed any of it is not admissible
    as evaluation or design evidence, however well it scored.
``operating_point``
    The hardware being designed. Changing it is the entire point of the design
    loop, so this is recorded, never refused.
``arm``
    How the crew operates the hardware. Recorded.

Differences are found by walking subtrees rather than by listing fields
(§11.4): a list of field names silently misses the neighbour that was added
next to it, and the neighbour of a threshold is usually another threshold.
Anything outside the three classes is still reported, under ``other``, so a
change can never disappear by being unclassified.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

SCORING_BAR = "scoring_bar"
OPERATING_POINT = "operating_point"
ARM = "arm"
OTHER = "other"

CLASSES = (SCORING_BAR, OPERATING_POINT, ARM, OTHER)

# Prefixes are matched against dotted paths, longest first, so a nested subtree
# can override the class of the subtree that contains it.
#
# Deviations from the literal list in §11.1, both in the direction of guarding
# more, are marked below. The spec asks for subtree diffing precisely because
# enumerating single fields misses their neighbours.
SCORING_BAR_PREFIXES: Tuple[str, ...] = (
    "thresholds",
    "plant_sim.survival",
    "plant_sim.habitat",  # not present in today's scenario; guarded if added
    "plant_sim.crew",
    # §11.1 names only initial_o2_storage_kg. Its neighbours are the same kind
    # of quantity -- how hard the run starts out -- so the whole set is guarded.
    "simulation.initial_o2_storage_kg",
    "simulation.initial_co2_storage_kg",
    "simulation.initial_product_water_l",
    # The scoring rules themselves, and the budgets and bounds that decide
    # whether a design may be adopted. Not in §11.1, but a run that rewrote
    # either of these would be reporting against its own yardstick.
    "evaluation",
    "design_constraints",
)

OPERATING_POINT_PREFIXES: Tuple[str, ...] = (
    "plant_sim.ars",
    "plant_sim.ogs",
    "plant_sim.wrs",
    "plant_sim.sabatier",
    "plant_sim.time",
    "plant_sim.operations",
    "backend",
)

ARM_PREFIXES: Tuple[str, ...] = ("agents",)

_PREFIX_CLASSES: Tuple[Tuple[str, str], ...] = tuple(
    sorted(
        [(prefix, SCORING_BAR) for prefix in SCORING_BAR_PREFIXES]
        + [(prefix, OPERATING_POINT) for prefix in OPERATING_POINT_PREFIXES]
        + [(prefix, ARM) for prefix in ARM_PREFIXES],
        key=lambda item: len(item[0]),
        reverse=True,
    )
)


def classify_path(path: str) -> str:
    """Which class of change a dotted config path belongs to."""
    for prefix, kind in _PREFIX_CLASSES:
        if path == prefix or path.startswith(prefix + "."):
            return kind
    return OTHER


def _changed_paths(
    pristine: Any, effective: Any, prefix: str = "", out: List[str] | None = None
) -> List[str]:
    """Dotted paths whose leaf value differs between two config trees.

    A subtree that appears or disappears wholesale is reported at the point it
    diverges, not leaf by leaf: the useful fact is that the branch changed.
    """
    paths = [] if out is None else out
    if isinstance(pristine, Mapping) and isinstance(effective, Mapping):
        for key in sorted(set(pristine) | set(effective)):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in pristine or key not in effective:
                paths.append(child)
                continue
            _changed_paths(pristine[key], effective[key], child, paths)
        return paths
    if pristine != effective and prefix:
        paths.append(prefix)
    return paths


def compare_configs(
    pristine: Mapping[str, Any], effective: Mapping[str, Any]
) -> Dict[str, Any]:
    """Classify every difference between the pristine and effective config."""
    changed: Dict[str, List[str]] = {kind: [] for kind in CLASSES}
    for path in _changed_paths(dict(pristine), dict(effective)):
        changed[classify_path(path)].append(path)

    return {
        "scoring_bar_modified": bool(changed[SCORING_BAR]),
        "operating_point_modified": bool(changed[OPERATING_POINT]),
        "arm_modified": bool(changed[ARM]),
        "changed_paths": changed,
    }


def evidence_status(integrity: Mapping[str, Any]) -> str:
    """``invalid`` when the run rewrote what it is judged by, else ``valid``."""
    return "invalid" if integrity.get("scoring_bar_modified") else "valid"


def integrity_summary(integrity: Mapping[str, Any]) -> Dict[str, Any]:
    """The compact block embedded in evaluation.json (spec §16)."""
    return {
        "scoring_bar_modified": bool(integrity.get("scoring_bar_modified")),
        "operating_point_modified": bool(integrity.get("operating_point_modified")),
        "arm_modified": bool(integrity.get("arm_modified")),
    }


__all__ = [
    "ARM",
    "CLASSES",
    "OPERATING_POINT",
    "OTHER",
    "SCORING_BAR",
    "classify_path",
    "compare_configs",
    "evidence_status",
    "integrity_summary",
]

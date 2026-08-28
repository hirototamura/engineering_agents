"""Optional progress hooks for chained ssos_eclss_loop runs."""

from __future__ import annotations

from typing import Any, Dict


class IterateReporter:
    """No-op reporter. CLI subclasses this for a live terminal UI."""

    def on_run_start(
        self,
        *,
        index: int,
        total: int,
        label: str,
        steps: int,
        kind: str = "iteration",
    ) -> None:
        return

    def on_step(self, *, step: int, steps: int) -> None:
        return

    def on_phase(self, detail: str) -> None:
        return

    def on_run_end(self, row: Dict[str, Any]) -> None:
        return

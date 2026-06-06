"""Append-only JSONL event logging for simulation runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class EventLog:
    """Write structured records to named JSONL streams under a run directory."""

    STREAMS = (
        "messages",
        "telemetry",
        "health_metrics",
        "eps_telemetry",
        "events",
        "design_state",
        "memory_reasoning",
    )

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._handles: Dict[str, Any] = {}

    def append(self, stream: str, record: Dict[str, Any]) -> None:
        if stream not in self.STREAMS:
            raise ValueError(f"Unknown stream: {stream}. Expected one of {self.STREAMS}")
        path = self.output_dir / f"{stream}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_summary(self, summary: Dict[str, Any]) -> None:
        path = self.output_dir / "summary.json"
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()

    @classmethod
    def prepare_run_dir(cls, base_dir: Path, run_id: Optional[str] = None) -> Path:
        """Create (or recreate) a run output directory."""
        import shutil
        from datetime import datetime

        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = base_dir / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        return run_dir

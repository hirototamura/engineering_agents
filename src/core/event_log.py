"""Append-only JSONL event logging for simulation runs."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

RUN_DIRECTORY_MARKERS = (
    "summary.json",
    "telemetry.jsonl",
    "events.jsonl",
    "evaluation.json",
    "applied_proposals.json",
    "consumed_proposals.json",
)


def looks_like_run_directory(path: Path) -> bool:
    """True when *path* already holds simulation artifacts, not arbitrary files."""
    return path.is_dir() and any((path / name).is_file() for name in RUN_DIRECTORY_MARKERS)


def remove_run_directory(path: Path, *, force: bool = False) -> None:
    """Delete a run directory. Refuse to wipe a non-run tree unless *force*."""
    if not path.exists():
        return
    if path.is_file():
        raise ValueError(f"Refusing to delete file {path}")
    if any(path.iterdir()) and not looks_like_run_directory(path) and not force:
        raise ValueError(
            f"Refusing to delete {path}: it is not a simulation run directory "
            f"(missing {', '.join(RUN_DIRECTORY_MARKERS)}). Pass --force to override."
        )
    shutil.rmtree(path)


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
    def prepare_run_dir(
        cls,
        base_dir: Path,
        run_id: Optional[str] = None,
        *,
        force: bool = False,
    ) -> Path:
        """Create (or recreate) a run output directory."""
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = base_dir / run_id
        if run_dir.exists():
            remove_run_directory(run_dir, force=force)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

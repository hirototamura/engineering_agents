"""Named run artifacts (ADK ArtifactService analogue)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from core.event_log import EventLog


class ArtifactStore:
    """Read/write JSON and EventLog streams under a run directory."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)

    def read_json(self, name: str, *, under: Optional[Path] = None) -> Dict[str, Any]:
        path = (Path(under) if under is not None else self.run_dir) / name
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def write_json(
        self,
        name: str,
        payload: Mapping[str, Any],
        *,
        under: Optional[Path] = None,
    ) -> Path:
        root = Path(under) if under is not None else self.run_dir
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return path

    def append_event(self, stream: str, record: Dict[str, Any]) -> None:
        EventLog(self.run_dir).append(stream, record)

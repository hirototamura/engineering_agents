"""Per-agent session log (ADK SessionService analogue)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List


class SessionStore:
    """Append-only JSONL keyed by ``agent_id``. Agents do not read peers."""

    def __init__(self, root: Path):
        self.root = Path(root) / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def path_for(self, agent_id: str) -> Path:
        safe = str(agent_id).replace("/", "_")
        return self.root / f"{safe}.jsonl"

    def append(self, agent_id: str, record: Dict[str, Any]) -> None:
        path = self.path_for(agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._write_lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def load(self, agent_id: str) -> List[Dict[str, Any]]:
        path = self.path_for(agent_id)
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

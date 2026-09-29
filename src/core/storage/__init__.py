"""Thin ADK-style storage services behind a run directory.

Runner / agent loops stay where they are. These objects only persist session
events, named artifacts, and a claims table used to keep design records
internally consistent.
"""

from pathlib import Path

from core.storage.artifacts import ArtifactStore
from core.storage.claims import ClaimsRegistry
from core.storage.session import SessionStore

DESIGN_STORAGE_DIR = "design_storage"


class DesignStorage:
    """One storage cylinder under ``<run_dir>/design_storage/``."""

    def __init__(self, run_dir):
        self.run_dir = Path(run_dir)
        self.root = self.run_dir / DESIGN_STORAGE_DIR
        self.session = SessionStore(self.root)
        self.artifacts = ArtifactStore(self.run_dir)
        self.claims = ClaimsRegistry(self.root / "claims.json")


__all__ = [
    "DESIGN_STORAGE_DIR",
    "ArtifactStore",
    "ClaimsRegistry",
    "DesignStorage",
    "SessionStore",
]

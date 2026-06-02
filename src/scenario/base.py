from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class Scenario(ABC):
    @abstractmethod
    def load_config(self) -> Dict[str, Any]:
        """Return merged scenario configuration."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def scenario_dir(self) -> Path:
        ...

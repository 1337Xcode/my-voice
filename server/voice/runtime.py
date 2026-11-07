"""Everything one serving container loads once and shares across sessions."""

import time
from dataclasses import dataclass, field
from pathlib import Path

from voice.storage import models_dir


@dataclass
class Runtime:
    """The container's loaded state: timings now, models as later phases add them."""

    loaded_at: float = field(default_factory=time.time)
    load_seconds: float = 0.0

    @classmethod
    def load(cls) -> "Runtime":
        """Loads everything the server needs before it accepts traffic."""
        started = time.time()
        runtime = cls()
        runtime.load_seconds = round(time.time() - started, 2)
        return runtime

    def model_version(self, speaker: str) -> str:
        """The active model's name for this speaker, or 'stock' before his first model."""
        return "stock"

    def registry_path(self, speaker: str) -> Path:
        """Where this speaker's model registry lives on the speech-models volume."""
        return models_dir(speaker) / "registry.json"

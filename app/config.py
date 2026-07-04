from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    runtime_root: Path = Path("data/jobs")
    zip_retention: timedelta = timedelta(minutes=30)

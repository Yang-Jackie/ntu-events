"""Repository-local output paths and lazy Django setup for evaluation commands."""

import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def run_directory(value: str | Path) -> Path:
    root = (REPOSITORY_ROOT / "var/evaluations").resolve()
    candidate = Path(value)
    candidate = (candidate if candidate.is_absolute() else REPOSITORY_ROOT / candidate).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("Choose a run directory beneath var/evaluations")
    return candidate


def run_file(directory: Path, filename: str) -> Path:
    root = directory.resolve()
    candidate = (root / filename).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("Evaluation file escaped the run directory")
    return candidate


def bootstrap_django() -> None:
    sys.path.insert(0, str(REPOSITORY_ROOT / "apps/backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

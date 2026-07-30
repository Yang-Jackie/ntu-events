"""Repository-local entry point for the guided Telegram pipeline."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ntu_events_ingestion.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

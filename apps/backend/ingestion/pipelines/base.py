from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ingestion.models import IngestionJob


class IngestionPipeline(Protocol):
    key: str

    def normalize_options(self, options: dict | None) -> dict:
        """Validate supplied options and return the complete persisted options."""

    def execute(self, job: IngestionJob) -> None:
        """Process one already-claimed ingestion job."""

    def close(self) -> None:
        """Release resources initialized by this process."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from ingestion.canonicalization.decision_provider import (
    CanonicalizationDecisionProvider,
    OpenAICanonicalizationDecisionProvider,
)
from ingestion.canonicalization.workflow import process_candidate
from ingestion.models import CandidateStatus, EventCandidate
from ingestion.raw_storage import LocalRawContentStorage, RawContentStorage


class CanonicalizationWorkerRuntime:
    """Process READY candidates serially through the source-neutral workflow."""

    def __init__(
        self,
        *,
        decision_provider: CanonicalizationDecisionProvider | None = None,
        storage: RawContentStorage | None = None,
    ) -> None:
        self._decision_provider = decision_provider
        self._storage = storage

    def run_next_candidate(self) -> EventCandidate | None:
        candidate = (
            EventCandidate.objects.filter(
                status=CandidateStatus.READY,
                canonicalization_plan__isnull=True,
            )
            .order_by("created_at", "pk")
            .first()
        )
        if candidate is None:
            return None
        process_candidate(
            candidate_id=candidate.pk,
            decision_provider=self._get_decision_provider(),
            storage=self._get_storage(),
        )
        return candidate

    def close(self) -> None:
        if self._decision_provider is not None:
            self._decision_provider.close()
            self._decision_provider = None

    def _get_decision_provider(self) -> CanonicalizationDecisionProvider:
        if self._decision_provider is None:
            if not getattr(settings, "OPENAI_API_KEY", ""):
                raise RuntimeError("OPENAI_API_KEY is required for canonicalization")
            self._decision_provider = OpenAICanonicalizationDecisionProvider(
                model_name=settings.OPENAI_CANONICALIZATION_MODEL,
            )
        return self._decision_provider

    def _get_storage(self) -> RawContentStorage:
        if self._storage is None:
            self._storage = LocalRawContentStorage(Path(settings.RAW_STORAGE_ROOT))
        return self._storage

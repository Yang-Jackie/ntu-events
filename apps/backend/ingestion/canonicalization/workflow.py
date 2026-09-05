"""Compatibility exports for canonicalization workflow entry points."""

from ingestion.canonicalization.plan_editing import update_canonicalization_plan
from ingestion.canonicalization.planning import canonicalize_candidate
from ingestion.canonicalization.processing import process_candidate

__all__ = (
    "canonicalize_candidate",
    "process_candidate",
    "update_canonicalization_plan",
)

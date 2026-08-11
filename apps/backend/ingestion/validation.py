from __future__ import annotations

from dataclasses import dataclass

from ingestion.contracts import EventCandidatePayload
from ingestion.models import ValidationStatus


@dataclass(frozen=True)
class CandidateValidation:
    status: str
    errors: list[dict[str, str]]


def validate_candidate(candidate: EventCandidatePayload) -> CandidateValidation:
    errors: list[dict[str, str]] = []
    locations = [
        occurrence.raw_location.strip()
        for occurrence in candidate.occurrences
        if occurrence.raw_location and occurrence.raw_location.strip()
    ]
    normalized_locations = " ".join(locations).casefold()
    if not locations:
        errors.append(
            {
                "code": "LOCATION_MISSING",
                "field": "occurrences.raw_location",
                "message": "The source provides no physical location.",
            }
        )
    if any(marker in normalized_locations for marker in ("zoom", "virtual meeting", "online")):
        errors.append(
            {
                "code": "ONLINE_ONLY",
                "field": "occurrences.raw_location",
                "message": "Online-only events are outside the current physical-event scope.",
            }
        )
    if any(
        marker in normalized_locations
        for marker in ("national library", "victoria st", "victoria street")
    ):
        errors.append(
            {
                "code": "OUTSIDE_NTU_CAMPUS",
                "field": "occurrences.raw_location",
                "message": "The structured location is explicitly outside the NTU campus scope.",
            }
        )
    for index, occurrence in enumerate(candidate.occurrences):
        if (
            not occurrence.is_all_day
            and occurrence.end_date is not None
            and (occurrence.end_date - occurrence.start_date).days > 2
        ):
            errors.append(
                {
                    "code": "LONG_RUNNING_RANGE",
                    "field": f"occurrences.{index}",
                    "message": (
                        "A long timed range may describe a programme or deadline rather "
                        "than one continuous occurrence."
                    ),
                }
            )
    if candidate.ambiguities:
        errors.append(
            {
                "code": "SOURCE_AMBIGUITY",
                "field": "ambiguities",
                "message": "Structured source observations require review.",
            }
        )

    invalid_codes = {"ONLINE_ONLY", "OUTSIDE_NTU_CAMPUS"}
    if any(error["code"] in invalid_codes for error in errors):
        status = ValidationStatus.INVALID
    elif errors:
        status = ValidationStatus.REVIEW_REQUIRED
    else:
        status = ValidationStatus.VALID
    return CandidateValidation(status=status, errors=errors)

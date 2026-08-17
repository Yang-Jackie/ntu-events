from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from ingestion.contracts import (
    AttendanceMode,
    CandidateControlledValues,
    CandidateOccurrence,
    CandidateRegistration,
    EventCandidatePayload,
    RegistrationScope,
    TimePrecision,
)
from ingestion.models import ValidationStatus


class IssueSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class CandidateValidation:
    status: str
    issues: list[dict[str, object]]


def validate_candidate(
    candidate: EventCandidatePayload,
    reference_data: dict[str, Any],
) -> CandidateValidation:
    issues: list[dict[str, object]] = []

    if not candidate.title or not candidate.title.strip():
        _issue(
            issues,
            code="TITLE_MISSING",
            path="title",
            message="The source does not provide a usable event title.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )

    if not candidate.occurrences:
        _issue(
            issues,
            code="OCCURRENCE_MISSING",
            path="occurrences",
            message="The source does not provide an event occurrence.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    occurrence_refs = [occurrence.local_ref for occurrence in candidate.occurrences]
    duplicate_refs = {ref for ref in occurrence_refs if occurrence_refs.count(ref) > 1}
    for duplicate_ref in sorted(duplicate_refs):
        _issue(
            issues,
            code="OCCURRENCE_REFERENCE_DUPLICATE",
            path="occurrences",
            message=f"Occurrence reference {duplicate_ref!r} is used more than once.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )

    supported_venue_ids = {
        int(item["id"])
        for item in reference_data.get("venues", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    for index, occurrence in enumerate(candidate.occurrences):
        _validate_occurrence(
            occurrence,
            index=index,
            supported_venue_ids=supported_venue_ids,
            issues=issues,
        )

    known_occurrence_refs = set(occurrence_refs)
    for index, registration in enumerate(candidate.registrations):
        _validate_registration(
            registration,
            index=index,
            known_occurrence_refs=known_occurrence_refs,
            issues=issues,
        )

    classification_references = reference_data.get("classifications", {})
    for facet_name, selection in (
        ("formats", candidate.formats),
        ("topics", candidate.topics),
        ("purposes", candidate.purposes),
        ("audiences", candidate.audiences),
    ):
        entries = (
            classification_references.get(facet_name, [])
            if isinstance(classification_references, dict)
            else []
        )
        supported_codes = {
            str(item["code"])
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        }
        _validate_controlled_values(
            facet_name,
            selection,
            supported_codes=supported_codes,
            issues=issues,
        )

    for index, organizer in enumerate(candidate.organizers):
        if not organizer.name or not organizer.name.strip():
            _issue(
                issues,
                code="ORGANIZER_NAME_MISSING",
                path=f"organizers.{index}.name",
                message="An organizer entry has no usable name.",
                severity=IssueSeverity.WARNING,
                blocks_canonicalization=False,
            )

    _validate_optional_url(
        candidate.image_url,
        path="image_url",
        code="IMAGE_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )
    _validate_optional_url(
        candidate.source_url,
        path="source_url",
        code="SOURCE_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )

    if candidate.ambiguities:
        _issue(
            issues,
            code="SOURCE_AMBIGUITY",
            path="ambiguities",
            message="The extracted source facts contain an explicit ambiguity.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    status = ValidationStatus.REVIEW_REQUIRED if issues else ValidationStatus.READY
    return CandidateValidation(status=status, issues=issues)


def _validate_occurrence(
    occurrence: CandidateOccurrence,
    *,
    index: int,
    supported_venue_ids: set[int],
    issues: list[dict[str, object]],
) -> None:
    path = f"occurrences.{index}"
    if occurrence.start_date is None:
        _issue(
            issues,
            code="OCCURRENCE_DATE_MISSING",
            path=f"{path}.start_date",
            message="The occurrence has no start date.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    if (
        occurrence.start_date is not None
        and occurrence.end_date is not None
        and occurrence.end_date < occurrence.start_date
    ):
        _issue(
            issues,
            code="OCCURRENCE_END_BEFORE_START",
            path=path,
            message="The occurrence end date precedes its start date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    if occurrence.start_time is not None and occurrence.start_date is None:
        _issue(
            issues,
            code="OCCURRENCE_START_TIME_WITHOUT_DATE",
            path=f"{path}.start_time",
            message="The occurrence has a start time but no start date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if occurrence.end_time is not None and occurrence.end_date is None:
        _issue(
            issues,
            code="OCCURRENCE_END_TIME_WITHOUT_DATE",
            path=f"{path}.end_time",
            message="The occurrence has an end time but no end date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if occurrence.end_time is not None and occurrence.start_time is None:
        _issue(
            issues,
            code="OCCURRENCE_END_TIME_WITHOUT_START_TIME",
            path=f"{path}.end_time",
            message="The occurrence has an end time but no start time.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if (
        occurrence.start_date is not None
        and occurrence.end_date == occurrence.start_date
        and occurrence.start_time is not None
        and occurrence.end_time is not None
        and occurrence.end_time < occurrence.start_time
    ):
        _issue(
            issues,
            code="OCCURRENCE_END_BEFORE_START",
            path=path,
            message="The occurrence end time precedes its start time.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    if occurrence.is_all_day and (
        occurrence.start_time is not None or occurrence.end_time is not None
    ):
        _issue(
            issues,
            code="ALL_DAY_OCCURRENCE_HAS_TIME",
            path=path,
            message="An all-day occurrence also contains a time.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    if occurrence.time_precision == TimePrecision.EXACT and occurrence.start_time is None:
        _issue(
            issues,
            code="EXACT_TIME_MISSING",
            path=f"{path}.start_time",
            message="An exact occurrence has no start time.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if occurrence.time_precision == TimePrecision.DATE_ONLY and (
        occurrence.start_time is not None or occurrence.end_time is not None
    ):
        _issue(
            issues,
            code="DATE_ONLY_OCCURRENCE_HAS_TIME",
            path=path,
            message="A date-only occurrence also contains a time.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )

    raw_location = occurrence.raw_location.strip() if occurrence.raw_location else ""
    if occurrence.attendance_mode == AttendanceMode.UNKNOWN:
        _issue(
            issues,
            code="ATTENDANCE_MODE_UNKNOWN",
            path=f"{path}.attendance_mode",
            message="The occurrence attendance mode is unknown.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    if occurrence.attendance_mode in (AttendanceMode.IN_PERSON, AttendanceMode.HYBRID):
        if not raw_location:
            _issue(
                issues,
                code="LOCATION_MISSING",
                path=f"{path}.raw_location",
                message="An in-person attendance option has no source-provided location.",
                severity=IssueSeverity.ERROR,
                blocks_canonicalization=False,
            )
        if not occurrence.suggested_venue_ids:
            _issue(
                issues,
                code="VENUE_UNRESOLVED",
                path=f"{path}.suggested_venue_ids",
                message="The physical location is not linked to a supported venue.",
                severity=IssueSeverity.WARNING,
                blocks_canonicalization=False,
            )
    if occurrence.attendance_mode == AttendanceMode.ONLINE and occurrence.suggested_venue_ids:
        _issue(
            issues,
            code="ONLINE_OCCURRENCE_HAS_VENUE",
            path=f"{path}.suggested_venue_ids",
            message="An online-only occurrence also suggests a physical venue.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    unknown_venue_ids = sorted(set(occurrence.suggested_venue_ids) - supported_venue_ids)
    if unknown_venue_ids:
        _issue(
            issues,
            code="UNSUPPORTED_VENUE_REFERENCE",
            path=f"{path}.suggested_venue_ids",
            message=f"Unsupported venue references: {unknown_venue_ids}.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    if occurrence.attendance_mode in (AttendanceMode.ONLINE, AttendanceMode.HYBRID):
        if not occurrence.meeting_url:
            _issue(
                issues,
                code="ONLINE_ACCESS_MISSING",
                path=f"{path}.meeting_url",
                message="The source does not provide a meeting link for online attendance.",
                severity=IssueSeverity.WARNING,
                blocks_canonicalization=False,
            )
    elif occurrence.meeting_url:
        _issue(
            issues,
            code="IN_PERSON_OCCURRENCE_HAS_MEETING_URL",
            path=f"{path}.meeting_url",
            message=("An occurrence not marked online or hybrid also contains a meeting link."),
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    _validate_optional_url(
        occurrence.meeting_url,
        path=f"{path}.meeting_url",
        code="MEETING_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )


def _validate_registration(
    registration: CandidateRegistration,
    *,
    index: int,
    known_occurrence_refs: set[str],
    issues: list[dict[str, object]],
) -> None:
    path = f"registrations.{index}"
    if not registration.name or not registration.name.strip():
        _issue(
            issues,
            code="REGISTRATION_NAME_MISSING",
            path=f"{path}.name",
            message="The registration entry has no usable name.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    if registration.scope == RegistrationScope.OCCURRENCE:
        if not registration.occurrence_ref:
            _issue(
                issues,
                code="REGISTRATION_OCCURRENCE_REFERENCE_MISSING",
                path=f"{path}.occurrence_ref",
                message="An occurrence-scoped registration has no occurrence reference.",
                severity=IssueSeverity.ERROR,
                blocks_canonicalization=False,
            )
        elif registration.occurrence_ref not in known_occurrence_refs:
            _issue(
                issues,
                code="REGISTRATION_OCCURRENCE_REFERENCE_UNKNOWN",
                path=f"{path}.occurrence_ref",
                message="The registration references an occurrence that does not exist.",
                severity=IssueSeverity.ERROR,
                blocks_canonicalization=False,
            )
    elif registration.occurrence_ref:
        _issue(
            issues,
            code="EVENT_REGISTRATION_HAS_OCCURRENCE_REFERENCE",
            path=f"{path}.occurrence_ref",
            message="An event-scoped registration also contains an occurrence reference.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )

    if registration.opens_time is not None and registration.opens_date is None:
        _issue(
            issues,
            code="REGISTRATION_OPEN_TIME_WITHOUT_DATE",
            path=f"{path}.opens_time",
            message="The registration opening time has no opening date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if registration.closes_time is not None and registration.closes_date is None:
        _issue(
            issues,
            code="REGISTRATION_CLOSE_TIME_WITHOUT_DATE",
            path=f"{path}.closes_time",
            message="The registration closing time has no closing date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if (
        registration.opens_date is not None
        and registration.closes_date is not None
        and registration.closes_date < registration.opens_date
    ):
        _issue(
            issues,
            code="REGISTRATION_CLOSE_BEFORE_OPEN",
            path=path,
            message="Registration closes before it opens.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    if (
        registration.opens_date is not None
        and registration.closes_date == registration.opens_date
        and registration.opens_time is not None
        and registration.closes_time is not None
        and registration.closes_time < registration.opens_time
    ):
        _issue(
            issues,
            code="REGISTRATION_CLOSE_BEFORE_OPEN",
            path=path,
            message="Registration closes before it opens.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    _validate_optional_url(
        registration.url,
        path=f"{path}.url",
        code="REGISTRATION_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )


def _validate_controlled_values(
    facet_name: str,
    selection: CandidateControlledValues,
    *,
    supported_codes: set[str],
    issues: list[dict[str, object]],
) -> None:
    unknown_codes = sorted(set(selection.supported_codes) - supported_codes)
    if unknown_codes:
        _issue(
            issues,
            code="UNSUPPORTED_CLASSIFICATION_CODE",
            path=f"{facet_name}.supported_codes",
            message=f"Unsupported {facet_name} codes: {unknown_codes}.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    outside_values = sorted({value.strip() for value in selection.other_values if value.strip()})
    if outside_values:
        _issue(
            issues,
            code="UNMAPPED_CLASSIFICATION",
            path=f"{facet_name}.other_values",
            message=f"Unmapped {facet_name} values require review: {outside_values}.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )


def _validate_optional_url(
    value: str | None,
    *,
    path: str,
    code: str,
    issues: list[dict[str, object]],
    blocks_canonicalization: bool,
) -> None:
    if not value:
        return
    if not is_valid_http_url(value):
        _issue(
            issues,
            code=code,
            path=path,
            message="The value is not a valid HTTP or HTTPS URL.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=blocks_canonicalization,
        )


def is_valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _issue(
    issues: list[dict[str, object]],
    *,
    code: str,
    path: str,
    message: str,
    severity: IssueSeverity,
    blocks_canonicalization: bool,
) -> None:
    issues.append(
        {
            "code": code,
            "path": path,
            "message": message,
            "severity": severity.value,
            "blocks_canonicalization": blocks_canonicalization,
        }
    )

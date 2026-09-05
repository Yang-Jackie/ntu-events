from __future__ import annotations

from typing import Any

from ingestion.canonicalization.proposal_issues import hard_issue
from ingestion.contracts import ObjectOperation, RegistrationScope
from ingestion.http_urls import is_valid_http_url


def validate_object_changes(changes, path: str, issues: list[dict[str, Any]]) -> None:
    seen: set[int] = set()
    for index, change in enumerate(changes):
        if change.operation == ObjectOperation.ADD:
            if change.id is not None or change.value is None:
                issues.append(
                    hard_issue(
                        "ADD_OBJECT_INVALID", f"{path}.{index}", "ADD requires id null and a value."
                    )
                )
        elif change.operation == ObjectOperation.UPDATE:
            if change.id is None or change.value is None or not change.changed_fields:
                issues.append(
                    hard_issue(
                        "UPDATE_OBJECT_INVALID",
                        f"{path}.{index}",
                        "UPDATE requires an ID, value, and changed fields.",
                    )
                )
        elif change.id is None or change.value is not None or change.changed_fields:
            issues.append(
                hard_issue(
                    "REMOVE_OBJECT_INVALID",
                    f"{path}.{index}",
                    "REMOVE requires an ID and no value or changed fields.",
                )
            )
        if change.id is not None:
            if change.id in seen:
                issues.append(
                    hard_issue(
                        "OBJECT_CHANGE_DUPLICATE",
                        f"{path}.{index}.id",
                        "An object is changed more than once.",
                    )
                )
            seen.add(change.id)
        if len(change.changed_fields) != len(set(change.changed_fields)):
            issues.append(
                hard_issue(
                    "FIELD_CHANGE_DUPLICATE",
                    f"{path}.{index}.changed_fields",
                    "A field is changed more than once.",
                )
            )


def validate_occurrence_value(value, path, issues: list[dict[str, Any]], *, adding: bool) -> None:
    if adding and (
        value.start_date is None
        or value.sequence is None
        or value.time_precision is None
        or value.attendance_mode is None
        or value.is_all_day is None
        or value.occurrence_status is None
    ):
        issues.append(
            hard_issue(
                "OCCURRENCE_REQUIRED_FIELD_MISSING",
                path,
                "An occurrence is missing a field required by canonical storage.",
            )
        )
        return
    if value.start_date and value.end_date and value.end_date < value.start_date:
        issues.append(hard_issue("OCCURRENCE_TIME_INVALID", path, "Occurrence end precedes start."))
    if value.end_time is not None and (value.end_date is None or value.start_time is None):
        issues.append(
            hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "An end time requires both end date and start time.",
            )
        )
    if (
        value.start_date
        and value.end_date == value.start_date
        and value.start_time
        and value.end_time
        and value.end_time < value.start_time
    ):
        issues.append(hard_issue("OCCURRENCE_TIME_INVALID", path, "Occurrence end precedes start."))
    if value.is_all_day and (value.start_time is not None or value.end_time is not None):
        issues.append(
            hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "An all-day occurrence cannot contain times.",
            )
        )
    if value.time_precision and value.time_precision.value == "EXACT" and not value.start_time:
        issues.append(
            hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "An exact occurrence requires a start time.",
            )
        )
    if (
        value.time_precision
        and value.time_precision.value == "DATE_ONLY"
        and (value.start_time is not None or value.end_time is not None)
    ):
        issues.append(
            hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "A date-only occurrence cannot contain times.",
            )
        )
    if value.meeting_url and not is_valid_http_url(value.meeting_url):
        issues.append(
            hard_issue("MEETING_URL_INVALID", f"{path}.meeting_url", "Meeting URL is invalid.")
        )


def validate_registration_value(
    value,
    path,
    issues: list[dict[str, Any]],
    *,
    event,
    added_occurrence_refs,
) -> None:
    if value.scope is None:
        issues.append(
            hard_issue(
                "REGISTRATION_OWNER_INVALID",
                path,
                "Registration scope is required.",
            )
        )
        return
    if value.url and not is_valid_http_url(value.url):
        issues.append(
            hard_issue("REGISTRATION_URL_INVALID", f"{path}.url", "Registration URL is invalid.")
        )
    if value.scope == RegistrationScope.OCCURRENCE:
        valid_id = bool(
            event
            and value.occurrence_id
            and event.occurrences.filter(pk=value.occurrence_id).exists()
        )
        valid_ref = bool(value.occurrence_client_ref in added_occurrence_refs)
        if not (valid_id or valid_ref):
            issues.append(
                hard_issue(
                    "REGISTRATION_OWNER_INVALID",
                    path,
                    "Occurrence registration has no valid occurrence owner.",
                )
            )
    elif value.scope == RegistrationScope.EVENT:
        if value.occurrence_id is not None or value.occurrence_client_ref is not None:
            issues.append(
                hard_issue(
                    "REGISTRATION_OWNER_INVALID",
                    path,
                    "Event registration cannot reference an occurrence.",
                )
            )
    if value.opens_time is not None and value.opens_date is None:
        issues.append(
            hard_issue("REGISTRATION_TIME_INVALID", path, "Opening time requires a date.")
        )
    if value.closes_time is not None and value.closes_date is None:
        issues.append(
            hard_issue("REGISTRATION_TIME_INVALID", path, "Closing time requires a date.")
        )
    if value.opens_date and value.closes_date and value.closes_date < value.opens_date:
        issues.append(
            hard_issue("REGISTRATION_TIME_INVALID", path, "Registration closes before it opens.")
        )
    if (
        value.opens_date
        and value.closes_date == value.opens_date
        and value.opens_time
        and value.closes_time
        and value.closes_time < value.opens_time
    ):
        issues.append(
            hard_issue("REGISTRATION_TIME_INVALID", path, "Registration closes before it opens.")
        )


def unique_change_fields(changes, path, issues: list[dict[str, Any]]) -> None:
    fields = [item.field for item in changes]
    if len(fields) != len(set(fields)):
        issues.append(
            hard_issue("FIELD_CHANGE_DUPLICATE", path, "A field is changed more than once.")
        )

from ingestion.contracts import AttendanceMode, CandidateOccurrence, TimePrecision

from .validation_issues import IssueSeverity, add_issue, validate_optional_url


def validate_occurrence(
    occurrence: CandidateOccurrence,
    *,
    index: int,
    supported_venue_ids: set[int],
    issues: list[dict[str, object]],
) -> None:
    path = f"occurrences.{index}"
    if occurrence.start_date is None:
        add_issue(
            issues,
            code="OCCURRENCE_DATE_MISSING",
            path=f"{path}.start_date",
            message="The occurrence has no start date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if (
        occurrence.start_date is not None
        and occurrence.end_date is not None
        and occurrence.end_date < occurrence.start_date
    ):
        add_issue(
            issues,
            code="OCCURRENCE_END_BEFORE_START",
            path=path,
            message="The occurrence end date precedes its start date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    if occurrence.start_time is not None and occurrence.start_date is None:
        add_issue(
            issues,
            code="OCCURRENCE_START_TIME_WITHOUT_DATE",
            path=f"{path}.start_time",
            message="The occurrence has a start time but no start date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if occurrence.end_time is not None and occurrence.end_date is None:
        add_issue(
            issues,
            code="OCCURRENCE_END_TIME_WITHOUT_DATE",
            path=f"{path}.end_time",
            message="The occurrence has an end time but no end date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if occurrence.end_time is not None and occurrence.start_time is None:
        add_issue(
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
        add_issue(
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
        add_issue(
            issues,
            code="ALL_DAY_OCCURRENCE_HAS_TIME",
            path=path,
            message="An all-day occurrence also contains a time.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if occurrence.time_precision == TimePrecision.EXACT and occurrence.start_time is None:
        add_issue(
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
        add_issue(
            issues,
            code="DATE_ONLY_OCCURRENCE_HAS_TIME",
            path=path,
            message="A date-only occurrence also contains a time.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )

    raw_location = occurrence.raw_location.strip() if occurrence.raw_location else ""
    if occurrence.attendance_mode == AttendanceMode.UNKNOWN:
        add_issue(
            issues,
            code="ATTENDANCE_MODE_UNKNOWN",
            path=f"{path}.attendance_mode",
            message="The occurrence attendance mode is unknown.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    if occurrence.attendance_mode in (AttendanceMode.IN_PERSON, AttendanceMode.HYBRID):
        if not raw_location:
            add_issue(
                issues,
                code="LOCATION_MISSING",
                path=f"{path}.raw_location",
                message="An in-person attendance option has no source-provided location.",
                severity=IssueSeverity.ERROR,
                blocks_canonicalization=False,
            )
        if not occurrence.suggested_venue_ids:
            add_issue(
                issues,
                code="VENUE_UNRESOLVED",
                path=f"{path}.suggested_venue_ids",
                message="The physical location is not linked to a supported venue.",
                severity=IssueSeverity.WARNING,
                blocks_canonicalization=False,
            )
    if occurrence.attendance_mode == AttendanceMode.ONLINE and occurrence.suggested_venue_ids:
        add_issue(
            issues,
            code="ONLINE_OCCURRENCE_HAS_VENUE",
            path=f"{path}.suggested_venue_ids",
            message="An online-only occurrence also suggests a physical venue.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    unknown_venue_ids = sorted(set(occurrence.suggested_venue_ids) - supported_venue_ids)
    if unknown_venue_ids:
        add_issue(
            issues,
            code="UNSUPPORTED_VENUE_REFERENCE",
            path=f"{path}.suggested_venue_ids",
            message=f"Unsupported venue references: {unknown_venue_ids}.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    if occurrence.attendance_mode in (AttendanceMode.ONLINE, AttendanceMode.HYBRID):
        if not occurrence.meeting_url:
            add_issue(
                issues,
                code="ONLINE_ACCESS_MISSING",
                path=f"{path}.meeting_url",
                message="The source does not provide a meeting link for online attendance.",
                severity=IssueSeverity.WARNING,
                blocks_canonicalization=False,
            )
    elif occurrence.meeting_url:
        add_issue(
            issues,
            code="IN_PERSON_OCCURRENCE_HAS_MEETING_URL",
            path=f"{path}.meeting_url",
            message=("An occurrence not marked online or hybrid also contains a meeting link."),
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    validate_optional_url(
        occurrence.meeting_url,
        path=f"{path}.meeting_url",
        code="MEETING_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )

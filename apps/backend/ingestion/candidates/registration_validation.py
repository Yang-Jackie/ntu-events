from ingestion.contracts import CandidateRegistration, RegistrationScope

from .validation_issues import IssueSeverity, add_issue, validate_optional_url


def validate_registration(
    registration: CandidateRegistration,
    *,
    index: int,
    known_occurrence_refs: set[str],
    issues: list[dict[str, object]],
) -> None:
    path = f"registrations.{index}"
    if not any(
        (
            bool(registration.name and registration.name.strip()),
            bool(registration.url),
            bool(registration.instructions and registration.instructions.strip()),
            registration.opens_date is not None,
            registration.closes_date is not None,
        )
    ):
        add_issue(
            issues,
            code="REGISTRATION_EMPTY",
            path=path,
            message="The registration entry contains no useful information.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if not registration.name or not registration.name.strip():
        add_issue(
            issues,
            code="REGISTRATION_NAME_MISSING",
            path=f"{path}.name",
            message="The registration entry has no usable name.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    if registration.scope == RegistrationScope.OCCURRENCE:
        if not registration.occurrence_ref:
            add_issue(
                issues,
                code="REGISTRATION_OCCURRENCE_REFERENCE_MISSING",
                path=f"{path}.occurrence_ref",
                message="An occurrence-scoped registration has no occurrence reference.",
                severity=IssueSeverity.ERROR,
                blocks_canonicalization=True,
            )
        elif registration.occurrence_ref not in known_occurrence_refs:
            add_issue(
                issues,
                code="REGISTRATION_OCCURRENCE_REFERENCE_UNKNOWN",
                path=f"{path}.occurrence_ref",
                message="The registration references an occurrence that does not exist.",
                severity=IssueSeverity.ERROR,
                blocks_canonicalization=True,
            )
    elif registration.occurrence_ref:
        add_issue(
            issues,
            code="EVENT_REGISTRATION_HAS_OCCURRENCE_REFERENCE",
            path=f"{path}.occurrence_ref",
            message="An event-scoped registration also contains an occurrence reference.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )

    if registration.opens_time is not None and registration.opens_date is None:
        add_issue(
            issues,
            code="REGISTRATION_OPEN_TIME_WITHOUT_DATE",
            path=f"{path}.opens_time",
            message="The registration opening time has no opening date.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=False,
        )
    if registration.closes_time is not None and registration.closes_date is None:
        add_issue(
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
        add_issue(
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
        add_issue(
            issues,
            code="REGISTRATION_CLOSE_BEFORE_OPEN",
            path=path,
            message="Registration closes before it opens.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    validate_optional_url(
        registration.url,
        path=f"{path}.url",
        code="REGISTRATION_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )

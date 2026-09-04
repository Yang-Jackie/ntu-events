from enum import StrEnum

from ingestion.http_urls import is_valid_http_url


class IssueSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"


def add_issue(
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


def validate_optional_url(
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
        add_issue(
            issues,
            code=code,
            path=path,
            message="The value is not a valid HTTP or HTTPS URL.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=blocks_canonicalization,
        )

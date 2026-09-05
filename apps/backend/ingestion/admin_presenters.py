import json

from django.utils.html import format_html

from ingestion.models import EventCandidate


def payload_summary(payload: object) -> str:
    payload = payload if isinstance(payload, dict) else {}
    lines = [f"Title: {payload.get('title') or 'Unknown'}"]
    description = payload.get("description")
    if description:
        lines.append(f"Description: {description}")
    occurrences = payload.get("occurrences")
    if isinstance(occurrences, list):
        for index, occurrence in enumerate(occurrences, start=1):
            if not isinstance(occurrence, dict):
                continue
            date = occurrence.get("start_date") or "date unknown"
            start_time = occurrence.get("start_time") or "time unknown"
            mode = occurrence.get("attendance_mode") or "mode unknown"
            location = occurrence.get("raw_location") or "no physical location"
            lines.append(f"Occurrence {index}: {date} {start_time}; {mode}; {location}")
    registrations = payload.get("registrations")
    if isinstance(registrations, list) and registrations:
        lines.append(f"Registrations: {len(registrations)}")
    ambiguities = payload.get("ambiguities")
    if isinstance(ambiguities, list) and ambiguities:
        lines.append(f"Ambiguities: {len(ambiguities)}")
    return format_html('<pre style="white-space: pre-wrap">{}</pre>', "\n".join(lines))


def validation_issue_summary(candidate: EventCandidate) -> str:
    if not candidate.validation_issues:
        return "No validation issues"
    lines = []
    for issue in candidate.validation_issues:
        if not isinstance(issue, dict):
            lines.append(str(issue))
            continue
        blocking = "blocking" if issue.get("blocks_canonicalization") else "review"
        lines.append(
            f"[{issue.get('severity', 'WARNING')}/{blocking}] "
            f"{issue.get('code', 'UNKNOWN')} at {issue.get('path', '')}: "
            f"{issue.get('message', '')}"
        )
    return format_html('<pre style="white-space: pre-wrap">{}</pre>', "\n".join(lines))


def raw_payload(candidate: EventCandidate) -> str:
    rendered = json.dumps(
        candidate.extracted_payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return format_html('<pre style="white-space: pre-wrap">{}</pre>', rendered)

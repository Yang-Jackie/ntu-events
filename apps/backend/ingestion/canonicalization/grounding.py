from typing import Any

from ingestion.contracts import EventField, FieldOperation


def synthesis_flags(payload, proposal) -> list[dict[str, Any]]:
    descriptions: list[str] = []
    if proposal.add_event and proposal.add_event.description:
        descriptions.append(proposal.add_event.description)
    descriptions.extend(
        change.value
        for change in proposal.event_changes
        if change.field == EventField.DESCRIPTION
        and change.operation == FieldOperation.SET
        and change.value
    )
    source_description = (payload.description or "").strip()
    return [
        {
            "code": "SYNTHESIZED_DESCRIPTION",
            "path": "description",
            "message": (
                "The proposed description is synthesized rather than copied from the candidate."
            ),
        }
        for description in descriptions
        if description.strip() != source_description
    ]

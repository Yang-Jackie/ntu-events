from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from events.models import Event
from ingestion.contracts import (
    AttendanceMode,
    CandidateOccurrence,
    CanonicalizationAction,
    CanonicalizationProposal,
    EventCandidatePayload,
    TimePrecision,
)
from ingestion.model_outputs import ModelOutputError, ModelResult
from ingestion.pipelines.telegram.adapter import TelegramFetchResult, TelegramMessage
from ingestion.pipelines.telegram.contracts import (
    ExtractedMessage,
    ExtractionBatch,
    ScreeningBatch,
    ScreeningItem,
    ScreeningLabel,
)
from sources.models import Source, SourceType

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "sources" / "telegram" / "messages.json"


class FakeFetcher:
    def __init__(
        self,
        messages: list[TelegramMessage],
        *,
        latest_message_id: int | None = None,
    ):
        self.messages = messages
        self.latest_message_id = (
            latest_message_id
            if latest_message_id is not None
            else max((message.message_id for message in messages), default=None)
        )

    async def fetch(self, **_kwargs) -> TelegramFetchResult:
        return TelegramFetchResult(
            messages=self.messages,
            latest_message_id=self.latest_message_id,
        )


class FakeModels:
    screening_model = "gpt-5-nano"
    extraction_model = "gpt-5-mini"
    model_name = "gpt-5-mini"

    def __init__(self):
        self.screening_batch_sizes: list[int] = []
        self.extraction_batch_sizes: list[int] = []
        self.reference_data_snapshots: list[dict] = []
        self.response_count = 0
        self.canonicalization_contexts: list[dict] = []

    def screen(self, messages: list[TelegramMessage]) -> ModelResult[ScreeningBatch]:
        self.screening_batch_sizes.append(len(messages))
        return self._result(
            ScreeningBatch(
                results=[
                    ScreeningItem(
                        message_identity=message.identity,
                        decision=(
                            ScreeningLabel.EVENT
                            if message.message_id <= 12
                            else ScreeningLabel.NOT_EVENT
                        ),
                        reason="event details" if message.message_id <= 12 else "not an event",
                        confidence=0.95,
                    )
                    for message in messages
                ]
            )
        )

    def extract(
        self,
        messages: list[TelegramMessage],
        *,
        reference_data: dict,
    ) -> ModelResult[ExtractionBatch]:
        self.extraction_batch_sizes.append(len(messages))
        self.reference_data_snapshots.append(reference_data)
        venue_id = reference_data["venues"][0]["id"]
        return self._result(
            ExtractionBatch(
                results=[
                    ExtractedMessage(
                        message_identity=message.identity,
                        events=[
                            EventCandidatePayload(
                                title=f"Test event {message.message_id}",
                                occurrences=[
                                    CandidateOccurrence(
                                        local_ref="occurrence-1",
                                        start_date=date(2026, 8, 18),
                                        start_time=time(14),
                                        end_date=date(2026, 8, 18),
                                        end_time=time(16),
                                        time_precision=TimePrecision.EXACT,
                                        attendance_mode=AttendanceMode.IN_PERSON,
                                        raw_location="The Arc",
                                        suggested_venue_ids=[venue_id],
                                    )
                                ],
                                source_url=message.source_url,
                                overall_confidence=0.9,
                            )
                        ],
                    )
                    for message in messages
                ]
            )
        )

    def _result(self, parsed):
        self.response_count += 1
        return ModelResult(
            parsed=parsed,
            response_identifier=f"response-{self.response_count}",
            token_usage={"input_tokens": 100, "output_tokens": 20},
            raw_response=b"{}",
        )

    def decide(self, context: dict) -> ModelResult[CanonicalizationProposal]:
        self.canonicalization_contexts.append(context)
        return self._result(
            CanonicalizationProposal(
                action=CanonicalizationAction.LINK_ONLY,
                target_event_id=context["possible_matches"][0]["event_id"],
                reasoning="The edited source representation describes the same event.",
                add_event=None,
                event_changes=[],
                classification_changes=[],
                organizer_changes=[],
                occurrence_changes=[],
                registration_changes=[],
            )
        )

    def close(self) -> None:
        return None


class FirstExtractionBatchFails(FakeModels):
    def extract(
        self,
        messages: list[TelegramMessage],
        *,
        reference_data: dict,
    ) -> ModelResult[ExtractionBatch]:
        if messages[0].message_id == 1:
            self.extraction_batch_sizes.append(len(messages))
            raise RuntimeError("temporary provider failure")
        return super().extract(messages, reference_data=reference_data)


class ScreeningFails(FakeModels):
    def screen(self, messages: list[TelegramMessage]) -> ModelResult[ScreeningBatch]:
        self.screening_batch_sizes.append(len(messages))
        raise RuntimeError("temporary screening failure")


class BusinessIssueModels(FakeModels):
    def extract(
        self,
        messages: list[TelegramMessage],
        *,
        reference_data: dict,
    ) -> ModelResult[ExtractionBatch]:
        message = messages[0]
        venue_id = reference_data["venues"][0]["id"]
        return self._result(
            ExtractionBatch(
                results=[
                    ExtractedMessage(
                        message_identity=message.identity,
                        events=[
                            EventCandidatePayload(
                                title="Contradictory event",
                                occurrences=[
                                    CandidateOccurrence(
                                        local_ref="session-1",
                                        start_date=date(2026, 8, 19),
                                        end_date=date(2026, 8, 18),
                                        time_precision=TimePrecision.DATE_ONLY,
                                        attendance_mode=AttendanceMode.IN_PERSON,
                                        raw_location="The Arc",
                                        suggested_venue_ids=[venue_id],
                                    )
                                ],
                                source_url=message.source_url,
                            )
                        ],
                    )
                ]
            )
        )


class StructuralOutputFails(FakeModels):
    def extract(
        self,
        messages: list[TelegramMessage],
        *,
        reference_data: dict,
    ) -> ModelResult[ExtractionBatch]:
        raise ModelOutputError(
            "OpenAI response was incomplete: max_output_tokens",
            raw_response=b'{"status":"incomplete"}',
            response_identifier="response-incomplete",
            token_usage={"output_tokens": 20},
        )


class ConcurrentEventEditModels(FakeModels):
    def decide(self, context: dict) -> ModelResult[CanonicalizationProposal]:
        event = Event.objects.get(pk=context["possible_matches"][0]["event_id"])
        event.description = "Owner edit made while the model was deciding."
        event.save(update_fields=("description", "updated_at"))
        return super().decide(context)


def make_source() -> Source:
    return Source.objects.create(
        name="Test Telegram channel",
        source_type=SourceType.PUBLIC_CHANNEL,
        base_url="https://t.me/test_channel",
        adapter_key="telegram_text",
        configuration={"channel_id": 12345, "username": "test_channel"},
    )


def fixture_messages() -> list[TelegramMessage]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    retrieved_at = datetime(2026, 8, 10, 12, tzinfo=UTC)
    return [
        TelegramMessage(
            message_id=item["id"],
            channel_id=12345,
            channel_title="Test Telegram channel",
            channel_username="test_channel",
            source_url=f"https://t.me/test_channel/{item['id']}",
            published_at=datetime(2026, 8, 10, item["id"] % 12, tzinfo=UTC),
            edited_at=None,
            text=item["text"],
            reply_to_message_id=None,
            forwarded_from=None,
            retrieved_at=retrieved_at,
            content_hash=f"{item['id']:064x}",
        )
        for item in fixture["messages"]
    ]

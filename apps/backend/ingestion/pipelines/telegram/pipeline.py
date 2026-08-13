from __future__ import annotations

import asyncio
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from sources.models import CrawlRun, RunStatus

from ingestion.models import IngestionJob, JobStatus
from ingestion.pipelines.telegram.adapter import TelegramFetcher
from ingestion.pipelines.telegram.extraction import OpenAITelegramModels
from ingestion.pipelines.telegram.processing import process_telegram_messages
from ingestion.raw_storage import LocalRawContentStorage, RawContentStorage

TELEGRAM_PIPELINE_KEY = "telegram_text"
TELEGRAM_WORKER_VERSION = "telegram-m3-v1"

DEFAULT_OPTIONS = {
    "message_limit": 100,
    "overlap": 20,
    "screening_batch_size": 20,
    "extraction_batch_size": 5,
    "openai_concurrency": 10,
}
OPTION_BOUNDS = {
    "message_limit": (1, 1000),
    "overlap": (0, 100),
    "screening_batch_size": (1, 20),
    "extraction_batch_size": (1, 5),
    "openai_concurrency": (1, 10),
}


class TelegramTextPipeline:
    key = TELEGRAM_PIPELINE_KEY

    def __init__(
        self,
        *,
        fetcher: TelegramFetcher | None = None,
        models: OpenAITelegramModels | None = None,
        storage: RawContentStorage | None = None,
    ):
        # Construction is deliberately side-effect free. Provider resources are
        # initialized only when this process executes its first Telegram job.
        self._fetcher = fetcher
        self._models = models
        self._storage = storage

    def normalize_options(self, options: dict | None) -> dict[str, int]:
        supplied = options or {}
        unknown = sorted(set(supplied) - set(DEFAULT_OPTIONS))
        if unknown:
            raise ValueError(f"Unsupported Telegram ingestion job options: {unknown}")
        result = DEFAULT_OPTIONS | supplied
        for key, (minimum, maximum) in OPTION_BOUNDS.items():
            value = result[key]
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{key} must be an integer")
            if not minimum <= value <= maximum:
                raise ValueError(f"{key} must be between {minimum} and {maximum}")
        return result

    def execute(self, job: IngestionJob) -> None:
        if job.status != JobStatus.RUNNING:
            raise ValueError("Ingestion job must be claimed before execution")
        if job.pipeline_key != self.key:
            raise ValueError(f"Job {job.pk} is not configured for pipeline {self.key}")

        options = self.normalize_options(job.options)
        fetcher = self._get_fetcher()
        models = self._get_models()
        storage = self._get_storage()
        crawl = CrawlRun.objects.create(
            ingestion_job=job,
            source=job.source,
            started_at=timezone.now(),
            status=RunStatus.RUNNING,
            worker_version=TELEGRAM_WORKER_VERSION,
        )

        try:
            fetch_result = asyncio.run(
                fetcher.fetch(
                    source_configuration=job.source.configuration,
                    message_limit=options["message_limit"],
                    overlap=options["overlap"],
                )
            )
            messages = fetch_result.messages
            self._update_job(job, items_discovered=len(messages))
            result = process_telegram_messages(
                job=job,
                crawl=crawl,
                messages=messages,
                models=models,
                storage=storage,
                options=options,
            )
            self._complete_job(job, crawl, fetch_result.latest_message_id, result)
        except Exception as exc:
            now = timezone.now()
            crawl.status = RunStatus.FAILED
            crawl.completed_at = now
            crawl.error_type = type(exc).__name__
            crawl.error_message = str(exc)
            crawl.save(update_fields=("status", "completed_at", "error_type", "error_message"))
            raise

    def close(self) -> None:
        if self._models is not None:
            self._models.close()
            self._models = None

    def _get_fetcher(self) -> TelegramFetcher:
        if self._fetcher is None:
            api_id = getattr(settings, "TELEGRAM_API_ID", None)
            api_hash = getattr(settings, "TELEGRAM_API_HASH", "")
            if not api_id or not api_hash:
                raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
            self._fetcher = TelegramFetcher(
                api_id=int(api_id),
                api_hash=api_hash,
                session_path=Path(settings.TELEGRAM_SESSION_PATH),
            )
        return self._fetcher

    def _get_models(self) -> OpenAITelegramModels:
        if self._models is None:
            if not getattr(settings, "OPENAI_API_KEY", ""):
                raise RuntimeError("OPENAI_API_KEY is required")
            self._models = OpenAITelegramModels(
                screening_model=settings.OPENAI_SCREENING_MODEL,
                extraction_model=settings.OPENAI_EXTRACTION_MODEL,
            )
        return self._models

    def _get_storage(self) -> RawContentStorage:
        if self._storage is None:
            self._storage = LocalRawContentStorage(Path(settings.RAW_STORAGE_ROOT))
        return self._storage

    @staticmethod
    def _update_job(job: IngestionJob, **fields) -> None:
        fields["heartbeat_at"] = timezone.now()
        IngestionJob.objects.filter(pk=job.pk).update(**fields)
        for key, value in fields.items():
            setattr(job, key, value)

    @staticmethod
    def _complete_job(job, crawl, latest_message_id, result) -> None:
        failures = len(result.failure_ids)
        final_status = JobStatus.PARTIAL if failures else JobStatus.SUCCEEDED
        now = timezone.now()
        with transaction.atomic():
            job.status = final_status
            job.completed_at = now
            job.heartbeat_at = now
            job.items_screened = result.items_screened
            job.items_relevant = result.items_relevant
            job.items_extracted = result.items_extracted
            job.candidates_created = result.candidates_created
            job.failures_count = failures
            job.save(
                update_fields=(
                    "status",
                    "completed_at",
                    "heartbeat_at",
                    "items_screened",
                    "items_relevant",
                    "items_extracted",
                    "candidates_created",
                    "failures_count",
                )
            )
            crawl.status = RunStatus.PARTIAL if failures else RunStatus.SUCCEEDED
            crawl.completed_at = now
            crawl.items_discovered = result.items_screened
            crawl.items_processed = result.items_screened
            crawl.save(
                update_fields=(
                    "status",
                    "completed_at",
                    "items_discovered",
                    "items_processed",
                )
            )
            configuration = dict(job.source.configuration)
            if latest_message_id is not None:
                configuration["last_message_id"] = max(
                    int(configuration.get("last_message_id") or 0),
                    latest_message_id,
                )
            if result.failure_ids:
                configuration["pending_message_ids"] = sorted(
                    int(value) for value in result.failure_ids
                )
            else:
                configuration.pop("pending_message_ids", None)
            job.source.configuration = configuration
            if failures:
                job.source.last_failed_crawl_at = now
                job.source.save(
                    update_fields=("configuration", "last_failed_crawl_at", "updated_at")
                )
            else:
                job.source.last_successful_crawl_at = now
                job.source.save(
                    update_fields=("configuration", "last_successful_crawl_at", "updated_at")
                )

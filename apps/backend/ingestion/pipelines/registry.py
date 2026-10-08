from ingestion.pipelines.base import IngestionPipeline
from ingestion.pipelines.telegram import TelegramTextPipeline

_telegram = TelegramTextPipeline()

PIPELINES: dict[str, IngestionPipeline] = {
    _telegram.key: _telegram,
}

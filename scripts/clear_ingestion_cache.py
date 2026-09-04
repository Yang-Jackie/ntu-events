"""Clear local ingestion replay state and canonical Events while preserving setup data.

Run inside the backend container so this script uses the same database and raw
storage settings as the application:

    docker compose run --rm backend python scripts/clear_ingestion_cache.py
    docker compose run --rm backend python scripts/clear_ingestion_cache.py --execute

The first command is a preview. Stop the ingestion and canonicalization workers
before running the second command.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import transaction  # noqa: E402
from events.models import Event, EventObservation, EventRevision, EventSourceLink  # noqa: E402
from ingestion.models import (  # noqa: E402
    CandidateMatch,
    CanonicalizationPlan,
    EventCandidate,
    ExtractionRun,
    IngestionJob,
    IngestionRequest,
    MessageScreening,
    ModelInvocation,
)
from sources.models import RawSourceDocument, Source, SourceRepresentation  # noqa: E402


def record_counts() -> dict[str, int]:
    return {
        "canonical events": Event.objects.count(),
        "source representations": SourceRepresentation.objects.count(),
        "raw source documents": RawSourceDocument.objects.count(),
        "ingestion requests": IngestionRequest.objects.count(),
        "ingestion jobs": IngestionJob.objects.count(),
        "model invocations": ModelInvocation.objects.count(),
        "message screenings": MessageScreening.objects.count(),
        "extraction runs": ExtractionRun.objects.count(),
        "event candidates": EventCandidate.objects.count(),
        "candidate matches": CandidateMatch.objects.count(),
        "canonicalization plans": CanonicalizationPlan.objects.count(),
        "event revisions": EventRevision.objects.count(),
        "event observations": EventObservation.objects.count(),
        "event source links": EventSourceLink.objects.count(),
    }


def raw_entries(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return list(root.rglob("*"))


def validate_raw_root(root: Path) -> Path:
    resolved = root.resolve()
    repository = REPOSITORY_ROOT.resolve()
    if (
        resolved == Path(resolved.anchor)
        or resolved == repository
        or resolved in repository.parents
    ):
        raise RuntimeError(f"Refusing to clear unsafe raw storage root: {resolved}")
    return resolved


def clear_raw_storage(root: Path) -> tuple[int, int]:
    files_deleted = 0
    directories_deleted = 0
    entries = sorted(raw_entries(root), key=lambda path: len(path.parts), reverse=True)
    for path in entries:
        if path.is_symlink() or path.is_file():
            path.unlink()
            files_deleted += 1
        elif path.is_dir():
            path.rmdir()
            directories_deleted += 1
    return files_deleted, directories_deleted


def clear_database_state() -> None:
    with transaction.atomic():
        EventRevision.objects.all().delete()
        EventObservation.objects.all().delete()
        EventSourceLink.objects.filter(
            source_representation__in=SourceRepresentation.objects.all()
        ).delete()
        CanonicalizationPlan.objects.all().delete()
        CandidateMatch.objects.all().delete()
        EventCandidate.objects.all().delete()
        Event.objects.all().delete()
        ExtractionRun.objects.all().delete()
        MessageScreening.objects.all().delete()
        RawSourceDocument.objects.all().delete()
        ModelInvocation.objects.all().delete()
        IngestionJob.objects.all().delete()
        IngestionRequest.objects.all().delete()
        SourceRepresentation.objects.all().delete()

        for source in Source.objects.select_for_update():
            configuration = dict(source.configuration)
            configuration.pop("last_message_id", None)
            configuration.pop("pending_message_ids", None)
            source.configuration = configuration
            source.last_successful_crawl_at = None
            source.last_failed_crawl_at = None
            source.save(
                update_fields=(
                    "configuration",
                    "last_successful_crawl_at",
                    "last_failed_crawl_at",
                    "updated_at",
                )
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the reset. Without this flag, only print a preview.",
    )
    args = parser.parse_args()

    raw_root = validate_raw_root(Path(settings.RAW_STORAGE_ROOT))
    counts = record_counts()
    entries = raw_entries(raw_root)
    print("Ingestion cache reset preview:")
    for label, count in counts.items():
        print(f"  {label}: {count}")
    print(f"  raw storage entries: {len(entries)} ({raw_root})")
    print("Preserved: Sources, Telegram session, users, organizers, venues, and catalogs.")
    print("Safety requirement: stop both ingestion workers before executing this reset.")

    if not args.execute:
        print("Preview only. Rerun with --execute to clear this state.")
        return 0

    clear_database_state()
    files_deleted, directories_deleted = clear_raw_storage(raw_root)
    print(
        f"Cleared ingestion state and removed {files_deleted} raw file(s) "
        f"from {directories_deleted} directories."
    )
    print("Canonical Events and their dependent records were deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Freeze public source evidence for a local model comparison. No provider calls."""

import argparse
import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path

from .paths import bootstrap_django, run_directory


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def fingerprint():
    bootstrap_django()
    from events.models import Event, EventOccurrence, Registration
    from ingestion.models import CanonicalizationPlan, EventCandidate, IngestionJob
    from sources.models import Source

    models = [
        Event,
        EventOccurrence,
        Registration,
        Source,
        EventCandidate,
        IngestionJob,
        CanonicalizationPlan,
    ]
    return {
        m._meta.label: {
            "count": m.objects.count(),
            "sha256": digest(list(m.objects.order_by("pk").values())),
        }
        for m in models
    }


def raw(storage, document):
    return json.loads(storage.load(document.storage_key))


def synthetic(identity, text):
    return {
        "message_id": identity,
        "channel_id": 0,
        "channel_title": "Synthetic evaluation fixture",
        "channel_username": None,
        "source_url": f"https://example.com/evaluation/{identity}",
        "published_at": "2026-10-08T03:00:00+00:00",
        "edited_at": None,
        "retrieved_at": "2026-10-08T03:00:00+00:00",
        "text": text,
        "reply_to_message_id": None,
        "forwarded_from": None,
        "links": [],
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
    }


def main(args):
    OUT = run_directory(args.run_dir)
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError("Choose an empty run directory; preserve existing evaluation artifacts")
    bootstrap_django()
    from django.conf import settings
    from django.db import connection, transaction
    from ingestion.models import CanonicalizationPlan, EventCandidate, IngestionJob
    from ingestion.raw_storage import LocalRawContentStorage
    from ingestion.reference_data import build_candidate_reference_data
    from sources.models import RawSourceDocument

    REQUEST = args.request_id
    SEED = args.seed
    CHALLENGE_IDS = args.challenge_candidate or []
    storage = LocalRawContentStorage(Path(settings.RAW_STORAGE_ROOT))
    rng = random.Random(SEED)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != args.source_database:
                raise RuntimeError("Unexpected source database; check --source-database")
        before = fingerprint()
        if IngestionJob.objects.filter(status__in=["RUNNING", "QUEUED"]).exists():
            raise RuntimeError("Wait for ingestion to be idle before freezing the experiment")
        if EventCandidate.objects.filter(
            status="READY", canonicalization_plan__isnull=True
        ).exists():
            raise RuntimeError("Wait for canonicalization to be idle")
        documents = list(
            RawSourceDocument.objects.filter(
                ingestion_job__request_id=REQUEST,
                source_representation__source_id__in=args.source,
            )
            .select_related("source_representation")
            .order_by("pk")
        )
        by_id = {d.pk: d for d in documents}
        challenge = list(
            EventCandidate.objects.filter(pk__in=CHALLENGE_IDS).values_list(
                "extraction_run__raw_source_document_id", flat=True
            )
        )
        if len(challenge) != len(set(CHALLENGE_IDS)):
            raise RuntimeError("A challenge candidate does not exist")
        challenge = sorted(set(challenge))
        if any(pk not in by_id for pk in challenge):
            raise RuntimeError(
                "Challenge candidates must belong to the selected request and sources"
            )
        chosen = []
        for source_id in sorted(set(args.source)):
            pool = [
                d
                for d in documents
                if d.source_representation.source_id == source_id and d.pk not in challenge
            ]
            chosen.extend(
                (d, "representative") for d in rng.sample(pool, min(args.per_source, len(pool)))
            )
        chosen.extend((by_id[pk], "observed_failure") for pk in challenge)
        extraction = [
            {
                "id": f"document-{d.pk}",
                "stratum": stratum,
                "source_id": d.source_representation.source_id,
                "document_id": d.pk,
                "message": raw(storage, d),
            }
            for d, stratum in chosen
        ]
        fixtures = [
            (
                900001,
                "Attend the Timezone Workshop online on 10 October 2026 at "
                "20:00 UTC. This is one session. Join at https://example.com/join-a",
            ),
            (
                900002,
                "Attend the UTC Seminar online on 12 October 2026 from "
                "10:00 UTC to 11:30 UTC. Join at https://example.com/join-b",
            ),
            (
                900003,
                "Singapore Clock Workshop: 14 October 2026, 18:00+08:00 to "
                "19:00+08:00, online. Join at https://example.com/join-c",
            ),
            (
                900004,
                "Committee recruitment applications close on 12 October 2026. "
                "This notice does not advertise any meeting, interview, or attendable activity.",
            ),
        ]
        extraction.extend(
            {
                "id": f"synthetic-{pk}",
                "stratum": "synthetic_edge",
                "source_id": None,
                "document_id": None,
                "message": synthetic(pk, text),
            }
            for pk, text in fixtures
        )
        plans = list(
            CanonicalizationPlan.objects.filter(
                event_candidate__extraction_run__raw_source_document__ingestion_job__request_id=REQUEST,
                event_candidate__extraction_run__raw_source_document__source_representation__source_id__in=args.source,
                model_invocation__isnull=False,
            )
            .select_related(
                "event_candidate__extraction_run__raw_source_document", "model_invocation"
            )
            .order_by("pk")
        )
        rejected = [p for p in plans if p.status == "REJECTED"]
        representative = []
        for action, count in [("ADD", 3), ("UPDATE", 4), ("LINK_ONLY", 3)]:
            pool = [p for p in plans if p.status == "APPLIED" and p.action == action]
            representative.extend(rng.sample(pool, min(count, len(pool))))
        selected_plans = [(p, "representative") for p in representative]
        selected_plans.extend(
            (p, "observed_failure")
            for p in rng.sample(rejected, min(args.failure_limit, len(rejected)))
        )
        canonicalization = []
        for p, stratum in selected_plans:
            c = p.event_candidate
            context = {
                "event_candidate": {
                    "id": c.pk,
                    "version": c.edit_version,
                    "effective_payload": c.effective_payload,
                },
                "raw_document": raw(storage, c.extraction_run.raw_source_document),
                "possible_matches": p.match_snapshot,
                "catalog": p.model_invocation.reference_data_snapshot,
            }
            actual_hash = hashlib.sha256(
                json.dumps(
                    context, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            if actual_hash != p.model_invocation.input_hash:
                raise RuntimeError(f"Historical context mismatch for candidate {c.pk}")
            canonicalization.append(
                {
                    "id": f"candidate-{c.pk}",
                    "candidate_id": c.pk,
                    "stratum": stratum,
                    "context": context,
                    "context_sha256": actual_hash,
                }
            )
        dataset = {
            "version": 1,
            "request_id": REQUEST,
            "seed": SEED,
            "created_at": datetime.now(UTC).isoformat(),
            "reference_data": build_candidate_reference_data(),
            "extraction": extraction,
            "canonicalization": canonicalization,
            "source_fingerprint": before,
        }
    dataset["sha256"] = digest(dataset)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dataset.json").write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    labels = {
        "dataset_sha256": dataset["sha256"],
        "review_status": "DRAFT",
        "review_method": "Agent-drafted source-grounded; owner reviews ambiguities",
        "extraction": {
            c["id"]: {"status": "TODO", "expected_event_count": None, "checks": [], "notes": ""}
            for c in extraction
        },
        "canonicalization": {
            c["id"]: {
                "status": "TODO",
                "allowed_actions": [],
                "target_event_id": None,
                "checks": [],
                "notes": "",
            }
            for c in canonicalization
        },
    }
    (OUT / "reference_answers.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    (OUT / "source_fingerprint.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "dataset_sha256": dataset["sha256"],
                "extraction_count": len(extraction),
                "canonicalization_count": len(canonicalization),
                "extraction_selection": [
                    {"id": c["id"], "source": c["source_id"], "stratum": c["stratum"]}
                    for c in extraction
                ],
                "canonicalization_selection": [
                    {"id": c["id"], "stratum": c["stratum"]} for c in canonicalization
                ],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--request-id", type=int, required=True)
    parser.add_argument("--source", type=int, action="append", required=True)
    parser.add_argument("--source-database", default="ntu_events")
    parser.add_argument("--challenge-candidate", type=int, action="append")
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--failure-limit", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261008)
    arguments = parser.parse_args()
    if (
        arguments.request_id < 1
        or arguments.per_source < 1
        or arguments.failure_limit < 0
        or any(source < 1 for source in arguments.source)
    ):
        parser.error(
            "Request/source IDs and per-source count must be positive; "
            "failure limit cannot be negative"
        )
    main(arguments)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count, Q


def merge_candidate_reviews(apps, schema_editor):
    EventCandidate = apps.get_model("ingestion", "EventCandidate")
    CandidateReview = apps.get_model("ingestion", "CandidateReview")
    CandidateMatch = apps.get_model("ingestion", "CandidateMatch")
    CanonicalizationPlan = apps.get_model("ingestion", "CanonicalizationPlan")
    EventObservation = apps.get_model("events", "EventObservation")

    # Pre-plan canonical events already have an observation. Give those legacy
    # candidates an explicit applied LINK_ONLY plan so PROCESSED still means a
    # plan exists after this migration.
    for observation in EventObservation.objects.select_related("source_link").iterator():
        review = CandidateReview.objects.filter(
            event_candidate_id=observation.event_candidate_id
        ).first()
        if review is None or CanonicalizationPlan.objects.filter(review=review).exists():
            continue
        CanonicalizationPlan.objects.create(
            review=review,
            review_version=review.review_version,
            action="LINK_ONLY",
            status="APPLIED",
            target_event_id=observation.source_link.event_id,
            generated_proposal={},
            effective_proposal={},
            applied_version=1,
            applied_at=observation.created_at,
        )

    duplicate_plan_candidate_ids = list(
        CanonicalizationPlan.objects.values("review__event_candidate_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .values_list("review__event_candidate_id", flat=True)
    )
    if duplicate_plan_candidate_ids:
        raise RuntimeError(
            "Cannot merge CandidateReview: multiple canonicalization plans exist for "
            f"EventCandidate IDs {duplicate_plan_candidate_ids}."
        )

    for candidate in EventCandidate.objects.order_by("pk").iterator():
        review = CandidateReview.objects.filter(event_candidate_id=candidate.pk).first()
        plan = (
            CanonicalizationPlan.objects.filter(review__event_candidate_id=candidate.pk)
            .order_by("-created_at", "-pk")
            .first()
        )
        if review is None:
            candidate.effective_payload = candidate.extracted_payload
            candidate.status = "READY" if candidate.status == "READY" else "BLOCKED"
        else:
            candidate.effective_payload = review.effective_payload
            candidate.validation_issues = review.validation_issues
            candidate.status = "READY" if review.review_status == "READY" else "BLOCKED"
            candidate.has_manual_edits = review.has_manual_edits
            candidate.edit_version = review.review_version
            candidate.reviewer_notes = review.reviewer_notes
            candidate.edited_by_id = review.reviewed_by_id
            candidate.edited_at = review.reviewed_at
        if plan is not None:
            candidate.status = "PROCESSED"
            candidate.processed_at = plan.created_at
        candidate.save(
            update_fields=(
                "effective_payload",
                "validation_issues",
                "status",
                "has_manual_edits",
                "edit_version",
                "reviewer_notes",
                "edited_by_id",
                "edited_at",
                "processed_at",
            )
        )

    for match in CandidateMatch.objects.select_related("review").iterator():
        match.event_candidate_id = match.review.event_candidate_id
        match.save(update_fields=("event_candidate_id",))
    for plan in CanonicalizationPlan.objects.select_related("review").iterator():
        plan.event_candidate_id = plan.review.event_candidate_id
        plan.save(update_fields=("event_candidate_id",))


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("events", "0010_preserve_event_provenance"),
        ("ingestion", "0007_candidatematch_canonicalizationplan_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name="eventcandidate",
            old_name="payload",
            new_name="extracted_payload",
        ),
        migrations.RenameField(
            model_name="eventcandidate",
            old_name="validation_status",
            new_name="status",
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="effective_payload",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="edit_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="edited_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="edited_event_candidates",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="has_manual_edits",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="reviewer_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="eventcandidate",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="candidatematch",
            name="event_candidate",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="matches",
                to="ingestion.eventcandidate",
            ),
        ),
        migrations.AddField(
            model_name="canonicalizationplan",
            name="event_candidate",
            field=models.ForeignKey(
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="canonicalization_plans_during_migration",
                to="ingestion.eventcandidate",
            ),
        ),
        migrations.RunPython(merge_candidate_reviews, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="candidatematch",
            name="unique_candidate_match_per_review_version_event",
        ),
        migrations.RemoveConstraint(
            model_name="candidatematch",
            name="unique_candidate_match_rank_per_review_version",
        ),
        migrations.RemoveConstraint(
            model_name="canonicalizationplan",
            name="unique_canonicalization_plan_per_review_version",
        ),
        migrations.RemoveConstraint(
            model_name="candidatereview",
            name="candidate_review_version_positive",
        ),
        migrations.RemoveConstraint(
            model_name="candidatereview",
            name="candidate_review_processed_version_not_ahead",
        ),
        migrations.RemoveField(model_name="candidatematch", name="review"),
        migrations.RemoveField(model_name="candidatematch", name="review_version"),
        migrations.RemoveField(model_name="canonicalizationplan", name="review"),
        migrations.RemoveField(model_name="canonicalizationplan", name="review_version"),
        migrations.DeleteModel(name="CandidateReview"),
        migrations.AlterField(
            model_name="eventcandidate",
            name="effective_payload",
            field=models.JSONField(),
        ),
        migrations.AlterField(
            model_name="eventcandidate",
            name="status",
            field=models.CharField(
                choices=[
                    ("BLOCKED", "Blocked"),
                    ("READY", "Ready"),
                    ("PROCESSED", "Processed"),
                ],
                db_index=True,
                default="BLOCKED",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="eventcandidate",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="candidatematch",
            name="event_candidate",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="matches",
                to="ingestion.eventcandidate",
            ),
        ),
        migrations.AlterField(
            model_name="canonicalizationplan",
            name="event_candidate",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="canonicalization_plan",
                to="ingestion.eventcandidate",
            ),
        ),
        migrations.AlterModelOptions(
            name="candidatematch",
            options={"ordering": ("event_candidate_id", "rank")},
        ),
        migrations.AddConstraint(
            model_name="eventcandidate",
            constraint=models.CheckConstraint(
                condition=Q(edit_version__gte=1),
                name="event_candidate_edit_version_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="candidatematch",
            constraint=models.UniqueConstraint(
                fields=("event_candidate", "event"),
                name="unique_candidate_match_per_event",
            ),
        ),
        migrations.AddConstraint(
            model_name="candidatematch",
            constraint=models.UniqueConstraint(
                fields=("event_candidate", "rank"),
                name="unique_candidate_match_rank",
            ),
        ),
    ]

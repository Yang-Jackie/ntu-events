import json

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from pydantic import ValidationError as PydanticValidationError

from .candidates import CandidateVersionConflict, update_event_candidate
from .canonicalization import update_canonicalization_plan
from .contracts import CanonicalizationProposal, EventCandidatePayload
from .models import (
    CandidateMatch,
    CandidateStatus,
    CanonicalizationPlan,
    EventCandidate,
    ExtractionRun,
    IngestionJob,
    IngestionRequest,
    MessageScreening,
    ModelInvocation,
)


class EventCandidateAdminForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = EventCandidate
        fields = ("effective_payload", "reviewer_notes")
        widgets = {"effective_payload": forms.Textarea(attrs={"rows": 32, "cols": 120})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["expected_version"].initial = self.instance.edit_version

    def clean_effective_payload(self) -> dict:
        value = self.cleaned_data["effective_payload"]
        try:
            EventCandidatePayload.model_validate(value)
        except PydanticValidationError as exc:
            raise forms.ValidationError(
                "The payload does not match the event-candidate schema: "
                f"{exc.errors(include_url=False)}"
            ) from exc
        return value

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if not self.instance.pk or "expected_version" not in cleaned_data:
            return cleaned_data
        current_version = (
            EventCandidate.objects.filter(pk=self.instance.pk)
            .values_list("edit_version", flat=True)
            .first()
        )
        if current_version != cleaned_data["expected_version"]:
            raise ValidationError(
                "This candidate changed after the page was loaded. Reload and retry."
            )

        return cleaned_data


class CanonicalizationPlanAdminForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = CanonicalizationPlan
        fields = ("effective_proposal",)
        widgets = {"effective_proposal": forms.Textarea(attrs={"rows": 36, "cols": 120})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["expected_version"].initial = self.instance.plan_version

    def clean_effective_proposal(self) -> dict:
        value = self.cleaned_data["effective_proposal"]
        try:
            CanonicalizationProposal.model_validate(value)
        except PydanticValidationError as exc:
            raise forms.ValidationError(
                "The proposal does not match the canonicalization schema: "
                f"{exc.errors(include_url=False)}"
            ) from exc
        return value

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if not self.instance.pk or "expected_version" not in cleaned_data:
            return cleaned_data
        current = (
            CanonicalizationPlan.objects.filter(pk=self.instance.pk)
            .values_list("plan_version", flat=True)
            .first()
        )
        if current != cleaned_data["expected_version"]:
            raise ValidationError("This plan changed after the page was loaded. Reload and retry.")
        return cleaned_data


def _payload_summary(payload: object) -> str:
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


class IngestionJobInline(admin.TabularInline):
    model = IngestionJob
    extra = 0
    fields = ("source", "status", "items_discovered", "items_relevant", "candidates_created")
    readonly_fields = fields
    can_delete = False


@admin.register(IngestionRequest)
class IngestionRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "trigger", "status_display", "requested_by", "created_at")
    list_filter = ("trigger",)
    readonly_fields = ("trigger", "requested_by", "created_at", "status_display")
    inlines = (IngestionJobInline,)

    @admin.display(description="Status")
    def status_display(self, obj: IngestionRequest) -> str:
        return obj.status


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "status",
        "attempt_count",
        "items_discovered",
        "items_relevant",
        "candidates_created",
        "created_at",
    )
    list_filter = ("status", "pipeline_key", "source")
    search_fields = ("source__name", "worker_id", "error_type", "error_message")
    readonly_fields = (
        "request",
        "source",
        "pipeline_key",
        "status",
        "options",
        "available_at",
        "claimed_at",
        "heartbeat_at",
        "completed_at",
        "worker_id",
        "attempt_count",
        "items_discovered",
        "items_screened",
        "items_relevant",
        "items_extracted",
        "candidates_created",
        "failures_count",
        "error_type",
        "error_message",
        "created_at",
    )


@admin.register(ModelInvocation)
class ModelInvocationAdmin(admin.ModelAdmin):
    list_display = ("job", "stage", "batch_index", "model_name", "status", "started_at")
    list_filter = ("stage", "status", "model_name")
    search_fields = ("response_identifier", "input_hash", "error_message")
    readonly_fields = [field.name for field in ModelInvocation._meta.fields]


@admin.register(MessageScreening)
class MessageScreeningAdmin(admin.ModelAdmin):
    list_display = ("source_representation", "decision", "confidence", "job", "created_at")
    list_filter = ("decision", "job__source")
    search_fields = ("source_representation__external_identifier", "reason", "content_hash")
    readonly_fields = [field.name for field in MessageScreening._meta.fields]


@admin.register(ExtractionRun)
class ExtractionRunAdmin(admin.ModelAdmin):
    list_display = (
        "raw_source_document",
        "extractor_type",
        "extractor_version",
        "model_name",
        "status",
        "started_at",
    )
    list_filter = ("status", "extractor_type", "model_name")
    search_fields = (
        "raw_source_document__storage_key",
        "response_identifier",
        "error_message",
    )


@admin.register(EventCandidate)
class EventCandidateAdmin(admin.ModelAdmin):
    form = EventCandidateAdminForm
    list_display = (
        "title",
        "source_representation",
        "schema_version",
        "overall_confidence",
        "status",
        "has_manual_edits",
        "issue_count",
        "created_at",
    )
    list_filter = ("status", "has_manual_edits", "schema_version")
    search_fields = (
        "title",
        "source_representation__external_identifier",
    )
    readonly_fields = (
        "candidate_summary",
        "validation_issue_summary",
        "raw_payload",
        "extraction_run",
        "source_representation",
        "candidate_index",
        "schema_version",
        "title",
        "overall_confidence",
        "status",
        "has_manual_edits",
        "edit_version",
        "edited_by",
        "edited_at",
        "processed_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Candidate",
            {
                "fields": (
                    "candidate_summary",
                    "title",
                    "overall_confidence",
                    "status",
                    "effective_payload",
                    "reviewer_notes",
                    "expected_version",
                )
            },
        ),
        ("Validation issues", {"fields": ("validation_issue_summary",)}),
        (
            "Candidate lifecycle",
            {
                "fields": (
                    "has_manual_edits",
                    "edit_version",
                    "edited_by",
                    "edited_at",
                    "processed_at",
                    "updated_at",
                )
            },
        ),
        (
            "Provenance",
            {
                "fields": (
                    "source_representation",
                    "extraction_run",
                    "candidate_index",
                    "schema_version",
                    "created_at",
                )
            },
        ),
        ("Raw payload", {"classes": ("collapse",), "fields": ("raw_payload",)}),
    )

    @admin.display(description="Issues", ordering="status")
    def issue_count(self, obj: EventCandidate) -> int:
        return len(obj.validation_issues)

    @admin.display(description="Candidate overview")
    def candidate_summary(self, obj: EventCandidate) -> str:
        return _payload_summary(obj.effective_payload)

    @admin.display(description="Validation issues")
    def validation_issue_summary(self, obj: EventCandidate) -> str:
        if not obj.validation_issues:
            return "No validation issues"
        lines = []
        for issue in obj.validation_issues:
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

    @admin.display(description="Original extracted payload")
    def raw_payload(self, obj: EventCandidate) -> str:
        rendered = json.dumps(obj.extracted_payload, ensure_ascii=False, indent=2, sort_keys=True)
        return format_html('<pre style="white-space: pre-wrap">{}</pre>', rendered)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return obj is None or obj.status == CandidateStatus.BLOCKED

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def save_model(self, request, obj: EventCandidate, form, change: bool) -> None:
        try:
            updated = update_event_candidate(
                obj.pk,
                expected_version=form.cleaned_data["expected_version"],
                effective_payload=form.cleaned_data["effective_payload"],
                reviewer_notes=form.cleaned_data["reviewer_notes"],
                edited_by_id=request.user.pk,
            )
        except CandidateVersionConflict as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return
        for field in EventCandidate._meta.concrete_fields:
            setattr(obj, field.attname, getattr(updated, field.attname))
        if updated.status == CandidateStatus.READY:
            self.message_user(request, "Candidate repaired and READY for future processing.")
        else:
            self.message_user(
                request,
                "Candidate remains BLOCKED by validation issues.",
                level=messages.WARNING,
            )


@admin.register(CandidateMatch)
class CandidateMatchAdmin(admin.ModelAdmin):
    list_display = (
        "event_candidate",
        "rank",
        "event",
        "match_percentage",
        "created_at",
    )
    search_fields = ("event_candidate__title", "event__title")
    readonly_fields = [field.name for field in CandidateMatch._meta.fields]

    @admin.display(description="Match")
    def match_percentage(self, obj) -> str:
        return f"{float(obj.score) * 100:.2f}%"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(CanonicalizationPlan)
class CanonicalizationPlanAdmin(admin.ModelAdmin):
    form = CanonicalizationPlanAdminForm
    list_display = ("event_candidate", "action", "status", "target_event", "updated_at")
    list_filter = ("action", "status", "has_manual_edits")
    search_fields = ("event_candidate__title", "target_event__title", "application_error")
    readonly_fields = (
        "event_candidate",
        "action",
        "status",
        "target_event",
        "model_invocation",
        "match_snapshot",
        "generated_proposal",
        "validation_issues",
        "domain_flags",
        "grounding_flags",
        "has_manual_edits",
        "plan_version",
        "applied_version",
        "applied_snapshot",
        "application_error",
        "applied_at",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change) -> None:
        try:
            updated = update_canonicalization_plan(
                obj.pk,
                expected_version=form.cleaned_data["expected_version"],
                effective_proposal=form.cleaned_data["effective_proposal"],
            )
        except CandidateVersionConflict as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return
        for field in CanonicalizationPlan._meta.concrete_fields:
            setattr(obj, field.attname, getattr(updated, field.attname))
        self.message_user(request, f"Plan status: {updated.status}.")

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

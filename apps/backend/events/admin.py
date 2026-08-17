from urllib.parse import urlencode

from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html
from ingestion.models import (
    CandidateReview,
    CandidateReviewOccurrence,
    CandidateReviewRegistration,
)

from .models import (
    Event,
    EventAudience,
    EventFormat,
    EventOccurrence,
    EventOrganizer,
    EventProvenance,
    EventPurpose,
    EventTopic,
    OccurrenceVenue,
    Registration,
)


class EventOrganizerInline(admin.TabularInline):
    model = EventOrganizer
    extra = 0


class EventOccurrenceInline(admin.TabularInline):
    model = EventOccurrence
    extra = 0
    show_change_link = True
    fields = (
        "sequence",
        "label",
        "start_date",
        "start_time",
        "end_date",
        "end_time",
        "time_precision",
        "attendance_mode",
        "occurrence_status",
    )


class EventRegistrationInline(admin.TabularInline):
    model = Registration
    fk_name = "event"
    extra = 0


class EventProvenanceInline(admin.TabularInline):
    model = EventProvenance
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "occurrence_link",
        "publication_status",
        "verification_status",
        "updated_at",
    )
    list_filter = (
        "publication_status",
        "verification_status",
        "formats",
        "topics",
        "purposes",
        "audiences",
    )
    search_fields = ("title", "normalized_title", "description", "audience_notes")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("formats", "topics", "purposes", "audiences")
    inlines = (
        EventOrganizerInline,
        EventOccurrenceInline,
        EventRegistrationInline,
        EventProvenanceInline,
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(admin_occurrence_count=Count("occurrences"))

    @admin.display(description="Occurrences", ordering="admin_occurrence_count")
    def occurrence_link(self, obj: Event) -> str:
        count = getattr(obj, "admin_occurrence_count", None)
        if count is None:
            count = obj.occurrences.count()
        url = reverse("admin:events_eventoccurrence_changelist")
        filtered_url = f"{url}?{urlencode({'event__id__exact': obj.pk})}"
        label = "occurrence" if count == 1 else "occurrences"
        return format_html('<a href="{}">{} {}</a>', filtered_url, count, label)

    def has_change_permission(self, request, obj=None) -> bool:
        if obj is not None and CandidateReview.objects.filter(canonical_event=obj).exists():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and CandidateReview.objects.filter(canonical_event=obj).exists():
            return False
        return super().has_delete_permission(request, obj)


class OccurrenceVenueInline(admin.TabularInline):
    model = OccurrenceVenue
    extra = 0


class OccurrenceRegistrationInline(admin.TabularInline):
    model = Registration
    fk_name = "occurrence"
    extra = 0


@admin.register(EventOccurrence)
class EventOccurrenceAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "sequence",
        "label",
        "start_date",
        "start_time",
        "attendance_mode",
        "occurrence_status",
    )
    list_filter = (
        "event",
        "attendance_mode",
        "occurrence_status",
        "capacity_status",
        "time_precision",
        "is_all_day",
    )
    search_fields = ("event__title", "label", "raw_location_text", "meeting_url")
    inlines = (OccurrenceVenueInline, OccurrenceRegistrationInline)

    def has_change_permission(self, request, obj=None) -> bool:
        if obj is not None and CandidateReviewOccurrence.objects.filter(occurrence=obj).exists():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and CandidateReviewOccurrence.objects.filter(occurrence=obj).exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("name", "registration_type", "status", "event", "occurrence")
    list_filter = ("registration_type", "status", "time_precision")
    search_fields = ("name", "url", "instructions", "event__title")

    def has_change_permission(self, request, obj=None) -> bool:
        if (
            obj is not None
            and CandidateReviewRegistration.objects.filter(registration=obj).exists()
        ):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if (
            obj is not None
            and CandidateReviewRegistration.objects.filter(registration=obj).exists()
        ):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(EventProvenance)
class EventProvenanceAdmin(admin.ModelAdmin):
    list_display = ("event", "source_representation", "event_candidate", "is_primary_source")
    list_filter = ("is_primary_source",)
    search_fields = (
        "event__title",
        "source_representation__external_identifier",
        "event_candidate__title",
    )
    readonly_fields = [field.name for field in EventProvenance._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ClassificationAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "label", "description")
    ordering = ("sort_order", "label")


admin.site.register(EventFormat, ClassificationAdmin)
admin.site.register(EventTopic, ClassificationAdmin)
admin.site.register(EventPurpose, ClassificationAdmin)
admin.site.register(EventAudience, ClassificationAdmin)

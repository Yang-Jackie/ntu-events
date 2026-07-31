from django.contrib import admin

from .models import (
    Event,
    EventAudience,
    EventFormat,
    EventOccurrence,
    EventOrganizer,
    EventProvenance,
    EventPurpose,
    EventSeries,
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
    fields = (
        "sequence",
        "label",
        "start_date",
        "start_time",
        "end_date",
        "end_time",
        "time_precision",
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
        "publication_status",
        "verification_status",
        "series",
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


class SeriesRegistrationInline(admin.TabularInline):
    model = Registration
    fk_name = "series"
    extra = 0


@admin.register(EventSeries)
class EventSeriesAdmin(admin.ModelAdmin):
    list_display = ("title", "updated_at")
    search_fields = ("title", "description")
    inlines = (SeriesRegistrationInline,)


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
        "occurrence_status",
    )
    list_filter = ("occurrence_status", "capacity_status", "time_precision", "is_all_day")
    search_fields = ("event__title", "label", "raw_location_text")
    inlines = (OccurrenceVenueInline, OccurrenceRegistrationInline)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("name", "registration_type", "status", "series", "event", "occurrence")
    list_filter = ("registration_type", "status", "time_precision")
    search_fields = ("name", "url", "instructions", "event__title", "series__title")


@admin.register(EventProvenance)
class EventProvenanceAdmin(admin.ModelAdmin):
    list_display = ("event", "source_representation", "event_candidate", "is_primary_source")
    list_filter = ("is_primary_source",)
    search_fields = (
        "event__title",
        "source_representation__external_identifier",
        "event_candidate__title",
    )


class ClassificationAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "label", "description")
    ordering = ("sort_order", "label")


admin.site.register(EventFormat, ClassificationAdmin)
admin.site.register(EventTopic, ClassificationAdmin)
admin.site.register(EventPurpose, ClassificationAdmin)
admin.site.register(EventAudience, ClassificationAdmin)

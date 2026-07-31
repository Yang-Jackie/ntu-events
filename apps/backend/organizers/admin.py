from django.contrib import admin

from .models import Organizer


@admin.register(Organizer)
class OrganizerAdmin(admin.ModelAdmin):
    list_display = ("name", "organization_type", "school_or_unit", "is_official")
    list_filter = ("organization_type", "is_official")
    search_fields = ("name", "normalized_name", "school_or_unit")

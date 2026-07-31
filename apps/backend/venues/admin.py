from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Building, Venue, VenueAlias


class VenueAliasInline(admin.TabularInline):
    model = VenueAlias
    extra = 0


@admin.register(Building)
class BuildingAdmin(GISModelAdmin):
    list_display = ("name", "code", "campus_area", "is_active", "verified_at")
    list_filter = ("campus_area", "is_active")
    search_fields = ("name", "normalized_name", "code", "address", "postal_code")


@admin.register(Venue)
class VenueAdmin(GISModelAdmin):
    list_display = ("name", "building", "venue_type", "room_code", "is_verified")
    list_filter = ("venue_type", "is_verified", "building")
    search_fields = ("name", "normalized_name", "room_code", "building__name")
    inlines = (VenueAliasInline,)


@admin.register(VenueAlias)
class VenueAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "venue", "match_type", "confidence", "is_verified")
    list_filter = ("match_type", "is_verified")
    search_fields = ("alias", "normalized_alias", "venue__name")

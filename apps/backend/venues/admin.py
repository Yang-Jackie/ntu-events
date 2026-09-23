from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Building, Venue, VenueAlias


class VenueAliasInline(admin.TabularInline):
    model = VenueAlias
    extra = 0


@admin.register(Building)
class BuildingAdmin(GISModelAdmin):
    list_display = (
        "name",
        "code",
        "location_kind",
        "parent",
        "campus_area",
        "map_positioning_method",
        "map_verified_at",
        "is_active",
        "verified_at",
    )
    list_filter = ("location_kind", "campus_area", "map_positioning_method", "is_active")
    search_fields = ("name", "normalized_name", "code", "address", "postal_code")


@admin.register(Venue)
class VenueAdmin(GISModelAdmin):
    list_display = (
        "name",
        "code",
        "building",
        "venue_type",
        "level_code",
        "room_code",
        "is_verified",
    )
    list_filter = ("venue_type", "is_verified", "building")
    search_fields = ("name", "code", "normalized_name", "room_code", "building__name")
    inlines = (VenueAliasInline,)


@admin.register(VenueAlias)
class VenueAliasAdmin(admin.ModelAdmin):
    list_display = (
        "alias",
        "venue",
        "match_type",
        "confidence",
        "is_verified",
        "verified_at",
    )
    list_filter = ("match_type", "is_verified")
    search_fields = ("alias", "normalized_alias", "venue__name")

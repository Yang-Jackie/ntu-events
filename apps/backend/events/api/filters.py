from __future__ import annotations

import math
from typing import Any

from rest_framework import serializers

from events.models import AttendanceMode


class BoundingBoxField(serializers.CharField):
    default_error_messages = {
        "format": "Use four comma-separated numbers: west,south,east,north.",
        "range": "Longitude must be within -180..180 and latitude within -90..90.",
        "order": "The east and north bounds must be greater than west and south.",
    }

    def to_internal_value(self, data: Any) -> tuple[float, float, float, float]:
        value = super().to_internal_value(data)
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 4:
            self.fail("format")
        try:
            west, south, east, north = (float(part) for part in parts)
        except ValueError:
            self.fail("format")
        if not all(math.isfinite(item) for item in (west, south, east, north)):
            self.fail("range")
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            self.fail("range")
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            self.fail("range")
        if east <= west or north <= south:
            self.fail("order")
        return west, south, east, north


class EventListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=200,
        help_text="Case-insensitive search across event text and organizer names.",
    )
    date_from = serializers.DateField(
        required=False,
        help_text="Return occurrences whose effective end date is on or after this date.",
    )
    date_to = serializers.DateField(
        required=False,
        help_text="Return occurrences whose start date is on or before this date.",
    )
    attendance_mode = serializers.ChoiceField(
        required=False,
        choices=AttendanceMode.choices,
        help_text="Return occurrences with this attendance mode.",
    )
    format = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this format code.",
    )
    topic = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this topic code.",
    )
    purpose = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this purpose code.",
    )
    audience = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this audience code.",
    )
    building = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text="Return occurrences linked to a venue in this building ID.",
    )
    bbox = BoundingBoxField(
        required=False,
        help_text="WGS84 bounds formatted as west,south,east,north.",
    )
    ordering = serializers.ChoiceField(
        required=False,
        choices=("start_date", "-start_date"),
        default="start_date",
        help_text="Order by the earliest or latest matching occurrence date.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("date_from") and attrs.get("date_to"):
            if attrs["date_from"] > attrs["date_to"]:
                raise serializers.ValidationError("date_from must not be after date_to.")
        return attrs

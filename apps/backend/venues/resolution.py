"""Resolve explicit location wording against the reviewed registry, without guessing."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from django.db.models import Prefetch, Q

from .models import Building, Venue, VenueAlias, VenueType


def normalize_location(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value).casefold()
    value = re.sub(r"\blecture\s+theatre\s*", "lt", value)
    value = re.sub(r"\btutorial\s+room\s*", "tr", value)
    value = re.sub(r"\b(lt|tr|sr)\s*[-+]?\s*(\d+)", r"\1\2", value)
    value = re.sub(r"[^\w.@]", " ", value)
    return " ".join(value.split())


@dataclass(frozen=True)
class LocationResolution:
    venue_ids: tuple[int, ...]
    method: str


class VenueResolver:
    """One registry snapshot shared by all locations in a workflow or report."""

    def __init__(self):
        self.venues = {
            venue.pk: venue
            for venue in Venue.objects.filter(is_verified=True)
            .filter(Q(building__isnull=True) | Q(building__is_active=True))
            .select_related("building")
            .prefetch_related(
                Prefetch("aliases", queryset=VenueAlias.objects.filter(is_verified=True))
            )
            .order_by("pk")
        }
        self.parents = dict(Building.objects.filter(is_active=True).values_list("pk", "parent_id"))
        self.names: dict[str, set[int]] = {}
        self.rooms: dict[str, set[int]] = {}
        self.local_names: dict[str, set[int]] = {}
        self.fallbacks = {}
        for venue in self.venues.values():
            if venue.building and venue.code == venue.building.code:
                self.fallbacks[venue.building_id] = venue.pk
            names = [
                venue.name,
                venue.code,
                venue.room_code,
                *(a.alias for a in venue.aliases.all()),
            ]
            for name in names:
                if name:
                    self.names.setdefault(normalize_location(name), set()).add(venue.pk)
            if (
                venue.building
                and venue.code != venue.building.code
                and venue.venue_type != VenueType.BUILDING
            ):
                local_name = normalize_location(venue.name).removeprefix("ntu ")
                local_name = local_name.removesuffix(
                    " at " + normalize_location(venue.building.name)
                )
                self.local_names.setdefault(local_name, set()).add(venue.pk)
            for room in re.findall(r"\b(?:lt|tr|sr)\d+[a-z]?\b", normalize_location(venue.name)):
                self.rooms.setdefault(room, set()).add(venue.pk)
        # A retained seed synonym such as The Hive must not compete with its reviewed anchor.
        for ids in self.names.values():
            anchors = {self.venues[pk].building_id for pk in ids if pk in self.fallbacks.values()}
            ids.difference_update(
                {
                    pk
                    for pk in ids
                    if self.venues[pk].code is None
                    and self.venues[pk].venue_type == VenueType.BUILDING
                    and self.venues[pk].building_id in anchors
                }
            )
        self.patterns = {
            name: re.compile(r"(?<![\w.@])" + re.escape(name) + r"(?![\w.@])")
            for name in self.names
        }

    def _within(self, building_id: int | None, ancestor: int) -> bool:
        seen = set()
        while building_id is not None and building_id not in seen:
            if building_id == ancestor:
                return True
            seen.add(building_id)
            building_id = self.parents.get(building_id)
        return False

    def resolve(self, raw_location: str | None) -> LocationResolution:
        if re.search(
            r"\b(?:not|or|either|maybe|possibly|tba|tbc)\b|to be (?:announced|confirmed)",
            raw_location or "",
            re.IGNORECASE,
        ):
            return LocationResolution((), "unresolved")
        # A landmark after "near" is not the actual attendance location.
        target = re.split(
            r"\b(?:near|beside|opposite|next\s+to)\b",
            raw_location or "",
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        text = normalize_location(target)
        if not text:
            return LocationResolution((), "unresolved")
        hits = {name: ids for name, ids in self.names.items() if self.patterns[name].search(text)}
        contexts = {
            self.venues[pk].building_id
            for ids in hits.values()
            for pk in ids
            if pk in self.fallbacks.values()
        }
        selected = set()
        for ids in hits.values():
            # A short room label must also be unambiguous among contextual room labels.
            if len(ids) == 1:
                selected.update(ids)
        for room, ids in self.rooms.items():
            if not re.search(r"(?<![\w.@])" + re.escape(room) + r"(?![\w.@])", text):
                continue
            scoped = (
                {
                    pk
                    for pk in ids
                    if any(self._within(self.venues[pk].building_id, b) for b in contexts)
                }
                if contexts
                else ids
            )
            if not scoped and len(ids) == 1 and re.search(r"[&;]|\band\b", target, re.IGNORECASE):
                scoped = ids  # An explicit list can name places in different buildings.
            selected.difference_update(ids)
            if len(scoped) == 1:
                selected.update(scoped)
        for name, ids in self.local_names.items():
            if not re.search(r"(?<![\w.@])" + re.escape(name) + r"(?![\w.@])", text):
                continue
            scoped = {
                pk
                for pk in ids
                if any(self._within(self.venues[pk].building_id, b) for b in contexts)
            }
            if len(scoped) == 1:
                selected.difference_update(ids)
                selected.update(scoped)
        # Prefer a known room over its building or parent-complex fallback.
        for building_id, fallback_id in self.fallbacks.items():
            if any(
                pk != fallback_id and self._within(self.venues[pk].building_id, building_id)
                for pk in selected
            ):
                selected.discard(fallback_id)
        if not selected:
            return LocationResolution((), "unresolved")
        method = (
            "building_fallback"
            if all(pk in self.fallbacks.values() for pk in selected)
            else "reviewed_match"
        )
        return LocationResolution(tuple(sorted(selected)), method)

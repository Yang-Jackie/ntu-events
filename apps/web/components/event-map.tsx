"use client";

import type * as Leaflet from "leaflet";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import type { MapMarker } from "@/lib/discovery";

type EventMapProps = {
  bbox?: string;
  markers: MapMarker[];
  returnPath: string;
};

const ntuCentre: Leaflet.LatLngExpression = [1.3483, 103.6831];

export function EventMap({ bbox, markers, returnPath }: EventMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Leaflet.Map>(null);
  const syncMapRef = useRef<(() => void) | null>(null);
  const updateTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const suppressMoveRef = useRef(false);
  const mapOriginatedBboxRef = useRef<string>(undefined);
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryString = searchParams.toString();
  const latestPropsRef = useRef({ bbox, markers, queryString, returnPath });

  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;

    const initialize = async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !containerRef.current) return;
      const map = L.map(containerRef.current, {
        zoomControl: false,
        minZoom: 12,
        zoomAnimation: false,
        fadeAnimation: false,
        markerZoomAnimation: false,
      });
      mapRef.current = map;
      L.control.zoom({ position: "bottomright" }).addTo(map);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(map);
      const markerLayer = L.layerGroup().addTo(map);
      let appliedBbox: string | undefined;

      const setViewWithoutSync = (setView: () => void) => {
        suppressMoveRef.current = true;
        setView();
        window.setTimeout(() => {
          suppressMoveRef.current = false;
        }, 0);
      };

      const syncMap = () => {
        const current = latestPropsRef.current;
        markerLayer.clearLayers();
        addMarkers(L, markerLayer, current.markers, current.returnPath);

        const bboxChanged = current.bbox !== appliedBbox;
        const changeCameFromMap =
          current.bbox !== undefined &&
          current.bbox === mapOriginatedBboxRef.current;
        if (changeCameFromMap) mapOriginatedBboxRef.current = undefined;

        if (!bboxChanged && current.bbox) return;
        appliedBbox = current.bbox;
        if (changeCameFromMap) return;

        const parsedBounds = parseBounds(current.bbox);
        setViewWithoutSync(() => {
          if (parsedBounds) {
            map.fitBounds(parsedBounds, { animate: false });
          } else if (current.markers.length) {
            map.fitBounds(
              L.latLngBounds(
                current.markers.map((marker) => [
                  marker.latitude,
                  marker.longitude,
                ]),
              ),
              { padding: [48, 48], maxZoom: 17, animate: false },
            );
          } else {
            map.setView(ntuCentre, 15, { animate: false });
          }
        });
      };

      const updateBounds = () => {
        if (suppressMoveRef.current) return;
        clearTimeout(updateTimerRef.current);
        updateTimerRef.current = setTimeout(() => {
          if (cancelled || mapRef.current !== map) return;
          const bounds = map.getBounds();
          const nextBbox = [
            bounds.getWest(),
            bounds.getSouth(),
            bounds.getEast(),
            bounds.getNorth(),
          ]
            .map((value) => value.toFixed(5))
            .join(",");
          const current = latestPropsRef.current;
          if (nextBbox === current.bbox) return;
          mapOriginatedBboxRef.current = nextBbox;
          const next = new URLSearchParams(current.queryString);
          next.set("bbox", nextBbox);
          next.delete("building");
          next.delete("page");
          router.replace(`/?${next}`, { scroll: false });
        }, 450);
      };
      map.on("moveend", updateBounds);
      syncMapRef.current = syncMap;
      syncMap();
    };

    void initialize();

    return () => {
      cancelled = true;
      clearTimeout(updateTimerRef.current);
      syncMapRef.current = null;
      if (mapRef.current) {
        mapRef.current.stop();
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [router]);

  useEffect(() => {
    latestPropsRef.current = { bbox, markers, queryString, returnPath };
    syncMapRef.current?.();
  }, [bbox, markers, queryString, returnPath]);

  return (
    <div className="event-map-frame">
      <div
        className="event-map"
        ref={containerRef}
        aria-label="Map of event venues"
      />
      <div className="event-map__status">
        <strong>{markers.length}</strong> mapped{" "}
        {markers.length === 1 ? "place" : "places"}
      </div>
    </div>
  );
}

function addMarkers(
  L: typeof Leaflet,
  layer: Leaflet.LayerGroup,
  markers: MapMarker[],
  returnPath: string,
) {
  for (const marker of markers) {
    const icon = L.divIcon({
      className: "event-map-marker-wrap",
      html: `<span class="event-map-marker"><span>${marker.events.length}</span></span>`,
      iconAnchor: [18, 36],
      iconSize: [36, 36],
      popupAnchor: [0, -34],
    });
    const leafletMarker = L.marker([marker.latitude, marker.longitude], {
      icon,
    }).addTo(layer);
    leafletMarker.bindPopup(buildPopup(marker, returnPath), {
      className: "event-map-popup",
      minWidth: 210,
    });
  }
}

function parseBounds(
  value: string | undefined,
): Leaflet.LatLngBoundsExpression | null {
  if (!value) return null;
  const [west, south, east, north] = value.split(",").map(Number);
  if ([west, south, east, north].some((item) => !Number.isFinite(item)))
    return null;
  if (
    west === undefined ||
    south === undefined ||
    east === undefined ||
    north === undefined
  ) {
    return null;
  }
  return [
    [south, west],
    [north, east],
  ];
}

function buildPopup(marker: MapMarker, returnPath: string): HTMLElement {
  const root = document.createElement("div");
  root.className = "map-popup-content";
  const label = document.createElement("strong");
  label.textContent = marker.label;
  root.append(label);
  for (const event of marker.events) {
    const link = document.createElement("a");
    link.href = `/events/${event.id}?from=${encodeURIComponent(returnPath)}`;
    link.textContent = event.title;
    root.append(link);
  }
  return root;
}

"use client";

import type {
  LngLatBoundsLike,
  Map as MapLibreMap,
  Marker as MapLibreMarker,
} from "maplibre-gl";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import type { MapMarker } from "@/lib/discovery";
import { BASEMAP_STYLE_URL, MAPLIBRE_WORKER_URL } from "@/lib/map-config";

type EventMapProps = {
  bbox?: string;
  markers: MapMarker[];
  returnPath: string;
};

const ntuCentre: [longitude: number, latitude: number] = [103.6831, 1.3483];

export function EventMap({ bbox, markers, returnPath }: EventMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap>(null);
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
      const maplibre = await import("maplibre-gl");
      if (cancelled || !containerRef.current) return;
      maplibre.setWorkerUrl(MAPLIBRE_WORKER_URL);
      const map = new maplibre.Map({
        container: containerRef.current,
        style: BASEMAP_STYLE_URL,
        center: ntuCentre,
        zoom: 15,
        minZoom: 12,
        maxZoom: 19,
        dragRotate: false,
        pitchWithRotate: false,
        fadeDuration: 0,
      });
      mapRef.current = map;
      map.touchZoomRotate.disableRotation();
      map.addControl(
        new maplibre.NavigationControl({ showCompass: false }),
        "bottom-right",
      );
      let renderedMarkers: MapLibreMarker[] = [];
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
        renderedMarkers.forEach((marker) => marker.remove());
        renderedMarkers = addMarkers(
          maplibre,
          map,
          current.markers,
          current.returnPath,
        );

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
            map.fitBounds(parsedBounds, { duration: 0 });
          } else if (current.markers.length) {
            map.fitBounds(boundsFromMarkers(current.markers), {
              padding: 48,
              maxZoom: 17,
              duration: 0,
            });
          } else {
            map.jumpTo({ center: ntuCentre, zoom: 15 });
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
  maplibre: typeof import("maplibre-gl"),
  map: MapLibreMap,
  markers: MapMarker[],
  returnPath: string,
): MapLibreMarker[] {
  const renderedMarkers: MapLibreMarker[] = [];

  for (const marker of markers) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "event-map-marker-wrap";
    element.setAttribute(
      "aria-label",
      `${marker.label}: ${marker.events.length} ${marker.events.length === 1 ? "event" : "events"}`,
    );
    const pin = document.createElement("span");
    pin.className = "event-map-marker";
    const count = document.createElement("span");
    count.textContent = String(marker.events.length);
    pin.append(count);
    element.append(pin);

    const popup = new maplibre.Popup({
      className: "event-map-popup",
      maxWidth: "280px",
      offset: 34,
    }).setDOMContent(buildPopup(marker, returnPath));
    const renderedMarker = new maplibre.Marker({
      element,
      anchor: "bottom",
    });
    renderedMarker
      .setLngLat([marker.longitude, marker.latitude])
      .setPopup(popup)
      .addTo(map);
    renderedMarkers.push(renderedMarker);
  }

  return renderedMarkers;
}

function parseBounds(value: string | undefined): LngLatBoundsLike | null {
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
    [west, south],
    [east, north],
  ];
}

function boundsFromMarkers(markers: MapMarker[]): LngLatBoundsLike {
  const longitudes = markers.map((marker) => marker.longitude);
  const latitudes = markers.map((marker) => marker.latitude);
  return [
    [Math.min(...longitudes), Math.min(...latitudes)],
    [Math.max(...longitudes), Math.max(...latitudes)],
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

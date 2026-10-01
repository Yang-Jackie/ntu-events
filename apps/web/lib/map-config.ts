import type { StyleSpecification } from "maplibre-gl";

export const MAPLIBRE_WORKER_URL = "/maplibre/maplibre-gl-worker.mjs";

export const DEFAULT_BASEMAP_PROVIDER = "openfreemap";

export type BasemapProvider = "openfreemap" | "openstreetmap";

const OPENFREEMAP_STYLE_URL =
  process.env.NEXT_PUBLIC_BASEMAP_STYLE_URL?.trim() ||
  "https://tiles.openfreemap.org/styles/liberty";

const OPENSTREETMAP_STANDARD_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    "openstreetmap-standard": {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      minzoom: 0,
      maxzoom: 19,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>',
    },
  },
  layers: [
    {
      id: "openstreetmap-standard",
      type: "raster",
      source: "openstreetmap-standard",
    },
  ],
};

export function basemapProvider(value: string | undefined): BasemapProvider {
  return value === "openstreetmap" ? value : DEFAULT_BASEMAP_PROVIDER;
}

export function basemapStyle(
  provider: BasemapProvider,
): string | StyleSpecification {
  return provider === "openstreetmap"
    ? OPENSTREETMAP_STANDARD_STYLE
    : OPENFREEMAP_STYLE_URL;
}

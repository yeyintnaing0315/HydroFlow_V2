import { TileLayer } from "react-leaflet";

/** Dev: browser fetches tiles directly (Vite OSM proxy often times out). Prod: nginx proxy. */
export const BASEMAP_TILE_URL = import.meta.env.PROD
  ? "/map-tiles/osm/{z}/{x}/{y}.png"
  : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

export const BASEMAP_ATTRIBUTION = "© OpenStreetMap contributors";

export default function BasemapTileLayer() {
  return (
    <TileLayer
      attribution={BASEMAP_ATTRIBUTION}
      url={BASEMAP_TILE_URL}
      subdomains={import.meta.env.PROD ? undefined : ["a", "b", "c"]}
      maxZoom={19}
    />
  );
}

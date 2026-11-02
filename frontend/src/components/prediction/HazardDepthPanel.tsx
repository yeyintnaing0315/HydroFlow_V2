import { useEffect, useState } from "react";
import { api } from "../../api";

interface HazardSurface {
  status: string;
  detail?: string;
  jrc_depth_100y_max_m?: number | null;
  jrc_pct_inundated_100y?: number | null;
  hand_min_m?: number | null;
  hand_pct_lt_2m?: number | null;
  worldcover_pct_built_floodplain?: number | null;
  worldcover_pct_crop_floodplain?: number | null;
  hydrobasin_id?: string | null;
}

export default function HazardDepthPanel({ townshipId }: { townshipId: string }) {
  const [surface, setSurface] = useState<HazardSurface | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setError(null);
    api
      .predictionHazardSurface(townshipId)
      .then((data) => {
        if (active) setSurface(data);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Hazard layer unavailable");
      });
    return () => {
      active = false;
    };
  }, [townshipId]);

  if (error) {
    return <p className="hint">Floodplain map: {error}</p>;
  }
  if (!surface || surface.status !== "ready") {
    return <p className="hint">{surface?.detail ?? "Loading JRC/HAND hazard summary…"}</p>;
  }
  const depth = surface.jrc_depth_100y_max_m;
  const inundated = surface.jrc_pct_inundated_100y;
  return (
    <div className="hazard-depth-panel" aria-label="100-year floodplain summary">
      <p className="field-label">100-year floodplain (JRC v2.1 + HAND)</p>
      <div className="hazard-depth-grid">
        <div>
          <span>Max depth (100y)</span>
          <strong>{depth == null ? "—" : `${depth.toFixed(2)} m`}</strong>
        </div>
        <div>
          <span>Area inundated (100y)</span>
          <strong>{inundated == null ? "—" : `${inundated.toFixed(1)} %`}</strong>
        </div>
        <div>
          <span>Low HAND (&lt;2 m)</span>
          <strong>{surface.hand_pct_lt_2m == null ? "—" : `${surface.hand_pct_lt_2m.toFixed(1)} %`}</strong>
        </div>
        <div>
          <span>Built in floodplain</span>
          <strong>
            {surface.worldcover_pct_built_floodplain == null
              ? "—"
              : `${surface.worldcover_pct_built_floodplain.toFixed(1)} %`}
          </strong>
        </div>
      </div>
      {surface.hydrobasin_id ? <p className="hint">Catchment: {surface.hydrobasin_id}</p> : null}
    </div>
  );
}

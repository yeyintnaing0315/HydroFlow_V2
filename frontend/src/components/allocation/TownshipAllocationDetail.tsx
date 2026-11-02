import { useState } from "react";
import type { AllocationTownshipRow } from "../../types";
import { formatMeasure } from "./routeFormat";
import { PageControls, ViewDialog } from "../ViewDialog";

interface TownshipAllocationDetailProps {
  row: AllocationTownshipRow | undefined;
  depotLabel: (region: "east" | "west") => string;
}

export default function TownshipAllocationDetail({ row, depotLabel }: TownshipAllocationDetailProps) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const items = row?.line_items ?? [];
  const preview = items.slice(0, 4);
  const pageSize = 6;
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const pageItems = items.slice(page * pageSize, page * pageSize + pageSize);
  return (
    <section className="panel allocation-detail-panel" aria-label="Selected township allocation">
      <div className="section-heading">
        <h2>{row ? row.township_name : "Allocation"}</h2>
        {row ? <span className="source">{depotLabel(row.depot_region)}</span> : null}
      </div>
      {!row ? <p className="hint">Select a township to see its allocation.</p> : null}
      {row ? (
        <div className="allocation-detail-scroll">
          <div className="allocation-sex-grid" aria-label="Affected people and flood context">
            <div>
              <span>People</span>
              <strong>{row.population.toLocaleString()}</strong>
            </div>
            <div>
              <span>Priority</span>
              <strong>{row.priority}</strong>
            </div>
            <div>
              <span>Flood</span>
              <strong>
                {row.flood_probability == null ? "—" : `${Math.round(row.flood_probability * 100)}%`}
              </strong>
            </div>
          </div>
          <p className="allocation-context-line">
            Risk {row.risk_band ?? "—"} · Rain {formatMeasure(row.rainfall_mm)} mm · Discharge{" "}
            {formatMeasure(row.discharge_m3_s)} m³/s
          </p>
          <ul className="allocation-line-items">
            {preview.map((item) => (
              <li key={`${item.category_code}:${item.item_code ?? "fund"}`}>
                <span>{item.name}</span>
                <span>
                  {item.allocated.toLocaleString()} / {item.requested.toLocaleString()} {item.unit}
                  {item.allocated < item.requested ? <em className="shortage-tag">short</em> : null}
                </span>
              </li>
            ))}
          </ul>
          {items.length > 4 ? (
            <button type="button" className="text-link" onClick={() => { setPage(0); setOpen(true); }}>
              View items
            </button>
          ) : null}
        </div>
      ) : null}
      <ViewDialog title={row ? `${row.township_name} items` : "Items"} open={open} onClose={() => setOpen(false)}>
        <ul className="allocation-line-items">
          {pageItems.map((item) => (
            <li key={`${item.category_code}:${item.item_code ?? "fund"}`}>
              <span>{item.name}</span>
              <span>
                {item.allocated.toLocaleString()} / {item.requested.toLocaleString()} {item.unit}
              </span>
            </li>
          ))}
        </ul>
        <PageControls page={page} pages={pages} onPage={setPage} />
      </ViewDialog>
    </section>
  );
}

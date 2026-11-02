import { useState } from "react";
import type { AllocationTownshipRow } from "../../types";
import { PageControls, ViewDialog } from "../ViewDialog";

interface TownshipAllocationListProps {
  rows: AllocationTownshipRow[];
  selectedId: string | null;
  onSelect: (townshipId: string) => void;
  depotLabel: (region: "east" | "west") => string;
}

const PREVIEW = 4;
const PAGE = 6;

function TownshipButtons({
  rows,
  selectedId,
  onSelect,
  depotLabel,
}: TownshipAllocationListProps) {
  return (
    <ul className="allocation-township-list">
      {rows.map((row) => (
        <li key={row.township_id}>
          <button
            type="button"
            className={row.township_id === selectedId ? "is-selected" : ""}
            aria-pressed={row.township_id === selectedId}
            onClick={() => onSelect(row.township_id)}
          >
            <strong>{row.township_name}</strong>
            <span>
              {depotLabel(row.depot_region)} · {row.population.toLocaleString()} people
              {row.route_id ? ` · ${row.route_id}` : ""}
            </span>
            {row.has_shortage ? <em className="shortage-tag">Shortage</em> : null}
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function TownshipAllocationList({
  rows,
  selectedId,
  onSelect,
  depotLabel,
}: TownshipAllocationListProps) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const visiblePage = rows.slice(page * PAGE, page * PAGE + PAGE);
  return (
    <section className="panel allocation-township-panel" aria-label="Township allocations">
      <div className="section-heading">
        <h2>Townships</h2>
        <span className="source">{rows.length ? `${rows.length}` : ""}</span>
      </div>
      <div className="allocation-township-scroll">
        {!rows.length ? <p className="state">No high or severe townships for this date.</p> : null}
        <TownshipButtons
          rows={rows.slice(0, PREVIEW)}
          selectedId={selectedId}
          onSelect={onSelect}
          depotLabel={depotLabel}
        />
        {rows.length > PREVIEW ? (
          <button type="button" className="text-link" onClick={() => { setPage(0); setOpen(true); }}>
            View townships
          </button>
        ) : null}
      </div>
      <ViewDialog title="Townships" open={open} onClose={() => setOpen(false)}>
        <TownshipButtons rows={visiblePage} selectedId={selectedId} onSelect={onSelect} depotLabel={depotLabel} />
        <PageControls page={page} pages={pages} onPage={setPage} />
      </ViewDialog>
    </section>
  );
}

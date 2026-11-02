import { useEffect, useState } from "react";
import { api } from "../../api";
import { riskLabel } from "../prediction/mapUtils";
import type { FloodCaseItem, LoadState } from "../../types";

function formatDateRange(row: FloodCaseItem): string {
  if (row.start_date === row.end_date) return row.start_date;
  return `${row.start_date} → ${row.end_date}`;
}

export default function AllocationFloodHistory() {
  const [state, setState] = useState<LoadState>("loading");
  const [events, setEvents] = useState<FloodCaseItem[]>([]);
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    let active = true;
    setState("loading");
    api
      .floodCasesHighSevere({ level: "all", source: "all", view: "events", limit: 500 })
      .then((payload) => {
        if (!active) return;
        setEvents(payload.events);
        setState(payload.events.length ? "ready" : "empty");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Could not load flood history");
        setState("error");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="allocation-map-flood-history" aria-label="High and severe flood history">
      <h3 className="allocation-map-flood-history-title">High &amp; severe flood history</h3>
      {state === "loading" && <p className="state allocation-map-flood-history-state">Loading…</p>}
      {state === "error" && <p className="state error allocation-map-flood-history-state">{error}</p>}
      {state === "empty" && (
        <p className="state allocation-map-flood-history-state">No high or severe cases in the catalog.</p>
      )}
      {state === "ready" && (
        <div className="allocation-table-wrap allocation-map-flood-history-table">
          <table>
            <thead>
              <tr>
                <th scope="col">Place</th>
                <th scope="col">Level</th>
                <th scope="col">Dates</th>
              </tr>
            </thead>
            <tbody>
              {events.map((row) => (
                <tr key={`${row.source}-${row.township_id}-${row.start_date}-${row.level}`}>
                  <td>{row.place}</td>
                  <td>
                    <span className={`risk-pill risk-${row.level}`}>{riskLabel(row.level)}</span>
                  </td>
                  <td>
                    {formatDateRange(row)}
                    {row.days > 1 ? ` (${row.days} d)` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

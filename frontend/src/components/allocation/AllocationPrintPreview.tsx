import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { AllocationPlanResponse } from "../../types";
import { buildAllocationReport, downloadAllocationPlanPdf } from "../../allocationPlanPdf";
import { printMapRoutes, type PrintRouteMode } from "../../lib/allocationPrintRoutes";
import {
  planRouteSummaries,
  selectedRouteLabels,
  summarizePlanResources,
} from "../../lib/allocationPrintSummary";
import { townshipsFromPlan } from "../../lib/allocationPlanMap";
import AllocationOverviewMap from "./AllocationOverviewMap";

interface AllocationPrintPreviewProps {
  plan: AllocationPlanResponse;
  emphasizedTownshipId?: string | null;
  onClose: () => void;
}

export default function AllocationPrintPreview({
  plan,
  emphasizedTownshipId,
  onClose,
}: AllocationPrintPreviewProps) {
  const [routeMode, setRouteMode] = useState<PrintRouteMode>("single");
  const report = buildAllocationReport(plan);
  const summary = useMemo(() => summarizePlanResources(plan), [plan]);
  const routeGroups = useMemo(() => planRouteSummaries(plan), [plan]);
  const townshipRoutes = useMemo(() => selectedRouteLabels(plan), [plan]);
  const mapModel = useMemo(
    () => printMapRoutes(plan, routeMode, emphasizedTownshipId),
    [plan, routeMode, emphasizedTownshipId],
  );
  const townships = useMemo(() => townshipsFromPlan(plan), [plan]);
  const hasAlternates = plan.rows.some((row) => (row.route_options?.length ?? 0) >= 2);

  return createPortal(
    <div className="allocation-print-backdrop" role="presentation" onClick={onClose}>
      <div
        className="allocation-print-sheet allocation-print-sheet-landscape"
        role="dialog"
        aria-modal="true"
        aria-label="Allocation report"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="allocation-print-actions no-print">
          <button type="button" className="outline" onClick={() => window.print()}>
            Print
          </button>
          <button type="button" className="outline" onClick={() => void downloadAllocationPlanPdf(plan)}>
            Download PDF
          </button>
          <button type="button" className="text-link" onClick={onClose}>
            Close
          </button>
        </div>

        <header className="allocation-print-minimal-head">
          <p className="eyebrow">HydroFlow · Bago Region</p>
          <h2>{report.title}</h2>
          <p>{report.subtitle}</p>
          <p className="allocation-print-lead">
            Delivery summary for verified depot stock. Fund is shown separately from other relief units (one unit per
            person across {summary.skuTypes} SKUs; longyi split by sex).
          </p>
        </header>

        <section className="allocation-print-summary-grid" aria-label="Resource summary">
          <article>
            <span>Fund allocated</span>
            <strong>{summary.fundAllocatedMmk.toLocaleString()} MMK</strong>
          </article>
          <article>
            <span>Other relief units</span>
            <strong>{Math.round(summary.otherUnitsAllocated).toLocaleString()} units</strong>
          </article>
          <article>
            <span>Affected people</span>
            <strong>{summary.people.toLocaleString()}</strong>
          </article>
          <article>
            <span>Townships · shortages</span>
            <strong>
              {summary.townshipCount} · {summary.shortageLines}
            </strong>
          </article>
          <article className="allocation-print-summary-wide">
            <span>Depots</span>
            <strong>{summary.depotLabels.join(" · ")}</strong>
          </article>
        </section>

        <section className="allocation-print-map-section" aria-label="Route map">
          <div className="allocation-print-section-head">
            <h3>Route map</h3>
            <fieldset className="allocation-print-route-mode no-print">
              <legend>Routes on map</legend>
              <label>
                <input
                  type="radio"
                  name="print-route-mode"
                  checked={routeMode === "single"}
                  onChange={() => setRouteMode("single")}
                />
                Plan route only
              </label>
              <label>
                <input
                  type="radio"
                  name="print-route-mode"
                  checked={routeMode === "dual"}
                  disabled={!hasAlternates}
                  onChange={() => setRouteMode("dual")}
                />
                Plan + alternate{dualHint(hasAlternates)}
              </label>
            </fieldset>
          </div>
          <div className="allocation-print-map">
            <AllocationOverviewMap
              instanceKey={`allocation-print-map-${routeMode}`}
              townships={townships}
              depots={mapModel.depots}
              routes={mapModel.routes}
              focusTownshipId={emphasizedTownshipId}
            />
          </div>
          <p className="hint allocation-print-map-note">
            Solid line = selected or plan route. Dashed line = saved alternate (compare routes on the plan page to store
            options).
          </p>
        </section>

        <section className="allocation-print-routes-copy" aria-label="Route summary">
          <h3>Routes</h3>
          {routeGroups.length ? (
            <ul>
              {routeGroups.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="state">No grouped routes in this plan.</p>
          )}
          {townshipRoutes.length ? (
            <>
              <h4>Township delivery choice</h4>
              <ul>
                {townshipRoutes.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </>
          ) : null}
        </section>

        <section className="allocation-print-table-section" aria-label="Township supplies">
          <h3>Full SKU allocation (19 items)</h3>
          {report.tableBody.length ? (
            <div className="allocation-print-table-wrap">
              <table className="allocation-print-table" aria-label="Township supplies">
                <thead>
                  <tr>
                    {report.tableHead.map((cell) => (
                      <th key={cell}>{cell}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.tableBody.map((row, index) => (
                    <tr key={`row-${index}`}>
                      {row.map((cell, cellIndex) => (
                        <td key={`${index}-${cellIndex}`}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="state">No allocated items in this plan.</p>
          )}
        </section>

        <footer className="allocation-print-disclaimer">
          <p>{plan.disclaimer}</p>
          <p>
            Signed dispatch: ______________________ Date: __________ · Verified depot stock before confirm.
          </p>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

function dualHint(hasAlternates: boolean): string {
  return hasAlternates ? "" : " (compare routes first)";
}

import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { AllocationPlanResponse } from "../../types";
import { buildAllocationReport, downloadAllocationPlanPdf } from "../../allocationPlanPdf";
import { printMapRoutes, type PrintRoadRoute, type PrintRouteMode } from "../../lib/allocationPrintRoutes";
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
  /** Same OSRM legs the plan map is already showing. */
  roadRoutes?: Record<string, PrintRoadRoute>;
  roadsLoading?: boolean;
  onClose: () => void;
}

export default function AllocationPrintPreview({
  plan,
  emphasizedTownshipId,
  roadRoutes,
  roadsLoading = false,
  onClose,
}: AllocationPrintPreviewProps) {
  const [routeMode, setRouteMode] = useState<PrintRouteMode>("single");
  const report = buildAllocationReport(plan);
  const summary = useMemo(() => summarizePlanResources(plan), [plan]);
  const routeGroups = useMemo(() => planRouteSummaries(plan), [plan]);
  const townshipRoutes = useMemo(() => selectedRouteLabels(plan), [plan]);
  const mapModel = useMemo(
    () => printMapRoutes(plan, routeMode, emphasizedTownshipId, roadRoutes, roadsLoading),
    [plan, routeMode, emphasizedTownshipId, roadRoutes, roadsLoading],
  );
  const roadReady = mapModel.routes.some((route) => !route.dimmed && route.path.length > 2);
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
            One list per township. Each person receives the items below. Men and women longyi are counted separately.
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
              loadingMessage={roadsLoading && !roadReady ? "Loading road route…" : null}
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
          <h3>Items to deliver</h3>
          {report.slips.length ? (
            report.slips.map((slip) => (
              <article key={slip.townshipName} className="allocation-print-slip">
                <header className="allocation-print-slip-head">
                  <h4>{slip.townshipName}</h4>
                  <p>
                    <span>Male <strong>{slip.male}</strong></span>
                    <span>Female <strong>{slip.female}</strong></span>
                    <span>People <strong>{slip.people}</strong></span>
                    <span>Fund <strong>{slip.fund}</strong></span>
                  </p>
                </header>
                <div className="allocation-print-slip-columns">
                  {(["left", "right"] as const).map((column) => (
                    <div key={column}>
                      {slip.groups
                        .filter((group) => group.column === column)
                        .map((group) => (
                          <div key={group.id} className="allocation-print-slip-group">
                            <h5>{group.title}</h5>
                            <ul>
                              {group.lines.map((line) => (
                                <li key={line.name}>
                                  <span>{line.name}</span>
                                  <strong>{line.detail}</strong>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                    </div>
                  ))}
                </div>
              </article>
            ))
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

import { useMemo } from "react";
import type { AllocationTownshipRow } from "../../types";
import { ALLOCATION_SKU_COLUMNS, allocationSkuKey } from "../../lib/allocationCatalog";
import {
  formatAllocatedRequested,
  rowHasPerPersonRuleMismatch,
} from "../../lib/allocationPerPersonCheck";
import { formatDistance } from "./routeFormat";

interface AllocationTownshipSupplyTableProps {
  rows: AllocationTownshipRow[];
  /** Township id → route distance in meters (optional). */
  routeDistanceByTownship?: Record<string, number | null | undefined>;
  /** Highlight selected township row. */
  selectedTownshipId?: string | null;
  onSelectTownship?: (townshipId: string) => void;
  /** Pre-plan preview: hide supply columns and route. */
  previewOnly?: boolean;
  /** Dashboard after plan: compact columns only (no SKU columns). */
  dashboardPlanView?: boolean;
  /** Planning date shown in Date column when dashboardPlanView. */
  planningDate?: string;
}

function rowPlanningDate(
  row: AllocationTownshipRow & { date?: string; planning_date?: string },
  fallback: string | undefined,
): string {
  const fromRow = row.date ?? row.planning_date;
  if (fromRow) return fromRow.slice(0, 10);
  return fallback?.slice(0, 10) ?? "—";
}

export default function AllocationTownshipSupplyTable({
  rows,
  routeDistanceByTownship,
  selectedTownshipId,
  onSelectTownship,
  previewOnly = false,
  dashboardPlanView = false,
  planningDate,
}: AllocationTownshipSupplyTableProps) {
  const showDate = dashboardPlanView;
  const showRiskAndRoute = !previewOnly;
  const showSkuColumns = !previewOnly && !dashboardPlanView;

  const itemColumns = useMemo(() => {
    if (!showSkuColumns) return [];
    return ALLOCATION_SKU_COLUMNS.map((column) => [
      allocationSkuKey(column.category_code, column.item_code),
      { name: column.name, unit: column.unit },
    ] as const);
  }, [showSkuColumns]);

  const columnCount =
    1 +
    (showDate ? 1 : 0) +
    (showRiskAndRoute ? 2 : 0) +
    3 +
    itemColumns.length;

  const wrapClassName = [
    "allocation-table-wrap",
    "allocation-supply-table-wrap",
    dashboardPlanView ? "allocation-dashboard-plan-table-wrap" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const tableClassName = [
    "allocation-supply-table",
    "allocation-summary-table",
    dashboardPlanView ? "allocation-dashboard-plan-table" : "",
  ]
    .filter(Boolean)
    .join(" ");

  if (!rows.length) {
    return (
      <div className={wrapClassName}>
        <table className={tableClassName}>
          <thead>
            <tr>
              <th scope="col" className="allocation-col-township">
                Township
              </th>
              {showDate ? (
                <th scope="col" className="allocation-col-date">
                  Date
                </th>
              ) : null}
              {showRiskAndRoute ? <th scope="col" className="allocation-col-risk">Risk</th> : null}
              <th scope="col" className="allocation-col-numeric">
                Male
              </th>
              <th scope="col" className="allocation-col-numeric">
                Female
              </th>
              <th scope="col" className="allocation-col-numeric">
                People
              </th>
              {showRiskAndRoute ? (
                <th scope="col" className="allocation-col-route">
                  Route
                </th>
              ) : null}
              {showSkuColumns
                ? itemColumns.map(([key, meta]) => (
                    <th scope="col" key={key}>
                      {meta.name}
                      <span className="allocation-supply-unit"> ({meta.unit})</span>
                    </th>
                  ))
                : null}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={columnCount} className="allocation-summary-empty">
                No high or severe townships for this date.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className={wrapClassName}>
      <table className={tableClassName}>
        <thead>
          <tr>
            <th scope="col" className="allocation-col-township">
              Township
            </th>
            {showDate ? (
              <th scope="col" className="allocation-col-date">
                Date
              </th>
            ) : null}
            {showRiskAndRoute ? <th scope="col" className="allocation-col-risk">Risk</th> : null}
            <th scope="col" className="allocation-col-numeric">
              Male
            </th>
            <th scope="col" className="allocation-col-numeric">
              Female
            </th>
            <th scope="col" className="allocation-col-numeric">
              People
            </th>
            {showRiskAndRoute ? (
              <th scope="col" className="allocation-col-route">
                Route
              </th>
            ) : null}
            {showSkuColumns
              ? itemColumns.map(([key, meta]) => (
                  <th scope="col" key={key}>
                    {meta.name}
                    <span className="allocation-supply-unit"> ({meta.unit})</span>
                  </th>
                ))
              : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const male = row.affected_male ?? 0;
            const female = row.affected_female ?? 0;
            const peopleDisplay =
              row.population < 0 ? "—" : row.population.toLocaleString();
            const maleDisplay = male < 0 ? "—" : male.toLocaleString();
            const femaleDisplay = female < 0 ? "—" : female.toLocaleString();
            const mismatch = showSkuColumns && rowHasPerPersonRuleMismatch(row);
            const qtyByKey = new Map(
              row.line_items.map((item) => [allocationSkuKey(item.category_code, item.item_code), item]),
            );
            const distanceM = routeDistanceByTownship?.[row.township_id];
            const selectable = Boolean(onSelectTownship);
            return (
              <tr
                key={row.township_id}
                className={[
                  selectedTownshipId === row.township_id ? "is-selected" : "",
                  selectable ? "is-clickable" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={
                  onSelectTownship
                    ? () => {
                        onSelectTownship(row.township_id);
                      }
                    : undefined
                }
                onKeyDown={
                  onSelectTownship
                    ? (event) => {
                        if (event.key !== "Enter" && event.key !== " ") return;
                        event.preventDefault();
                        onSelectTownship(row.township_id);
                      }
                    : undefined
                }
                tabIndex={selectable ? 0 : undefined}
                role={selectable ? "button" : undefined}
              >
                <td className="allocation-col-township">
                  {row.township_name}
                  {mismatch ? (
                    <span className="shortage-tag allocation-rule-mismatch" title="Requested amounts differ from per-person rule">
                      rule mismatch
                    </span>
                  ) : null}
                </td>
                {showDate ? (
                  <td className="allocation-col-date">{rowPlanningDate(row, planningDate)}</td>
                ) : null}
                {showRiskAndRoute ? (
                  <td className="allocation-col-risk">
                    <span className={`risk-pill risk-${row.priority}`}>{row.priority}</span>
                  </td>
                ) : null}
                <td className="allocation-col-numeric">{maleDisplay}</td>
                <td className="allocation-col-numeric">{femaleDisplay}</td>
                <td className="allocation-col-numeric">{peopleDisplay}</td>
                {showRiskAndRoute ? (
                  <td className="allocation-col-route">{formatDistance(distanceM ?? undefined)}</td>
                ) : null}
                {showSkuColumns
                  ? itemColumns.map(([key]) => {
                      const item = qtyByKey.get(key);
                      if (!item) {
                        return (
                          <td key={key} className="allocation-col-numeric">
                            —
                          </td>
                        );
                      }
                      return (
                        <td key={key} className="allocation-col-numeric">
                          {formatAllocatedRequested(item.allocated, item.requested)}
                        </td>
                      );
                    })
                  : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

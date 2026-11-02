import type { AllocationPlanResponse, AllocationTownshipRow } from "./types";
import { formatDistance, formatDuration, routeMethodLabel } from "./components/allocation/routeFormat";

export interface AllocationReport {
  identity: string;
  depots: string;
  summary: string;
  disclaimer: string;
  townshipHead: string[];
  townshipBody: string[][];
  itemHead: string[];
  itemBody: string[][];
  shortageHead: string[];
  shortageBody: string[][];
  filename: string;
}

function unitLabel(unit: string): string {
  return unit.toLowerCase() === "mmk" ? "MMK" : unit;
}

function amount(value: number): string {
  return value.toLocaleString();
}

function depotName(plan: AllocationPlanResponse, region: "east" | "west"): string {
  const warehouses = plan.warehouses.length ? plan.warehouses : [plan.warehouse];
  const match = warehouses.find((warehouse) => warehouse.region === region);
  if (match) return match.name;
  return region === "east" ? "Bago (east)" : "Pyay (west)";
}

function routeCell(row: AllocationTownshipRow, plan: AllocationPlanResponse): string {
  const picked =
    row.route_options?.find((option) => option.selected) ??
    row.route_options?.find((option) => option.recommended);
  const group = plan.routes.find((route) => route.route_id === row.route_id);
  const name = picked?.label ?? group?.route_id ?? row.route_id;
  const method = picked?.routing_method ?? group?.routing_method;
  const distance = picked?.distance_m ?? group?.distance_m;
  const duration = picked?.duration_s ?? group?.duration_s;
  return [
    name,
    method ? routeMethodLabel(method) : "",
    distance != null ? formatDistance(distance) : "",
    duration != null ? formatDuration(duration) : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function filePart(value: string): string {
  return value.replace(/[^\w.-]+/g, "-");
}

export function buildAllocationReport(plan: AllocationPlanResponse): AllocationReport {
  const depots = (plan.warehouses.length ? plan.warehouses : [plan.warehouse]).map((depot) => depot.name);
  return {
    identity: `Plan ${plan.plan_id} · ${plan.planning_date} · ${plan.model_version}${plan.status ? ` · ${plan.status}` : ""}`,
    depots: depots.join(" · "),
    summary: `Affected people: ${amount(plan.totals.affected_population)} · Townships: ${amount(plan.rows.length)} · Shortage lines: ${amount(plan.shortages.length)}`,
    disclaimer: plan.disclaimer,
    townshipHead: ["Township", "Depot", "People", "Priority", "Route"],
    townshipBody: plan.rows.map((row) => [
      row.township_name,
      depotName(plan, row.depot_region),
      amount(row.population),
      row.priority,
      routeCell(row, plan),
    ]),
    itemHead: ["Township", "Item", "Unit", "Requested", "Allocated"],
    itemBody: plan.rows.flatMap((row) =>
      row.line_items.map((item) => [
        row.township_name,
        item.name,
        unitLabel(item.unit),
        amount(item.requested),
        amount(item.allocated),
      ]),
    ),
    shortageHead: ["Item", "Unit", "Depot", "Requested", "Available", "Unmet"],
    shortageBody: plan.shortages.map((item) => [
      item.name,
      unitLabel(item.unit),
      depotName(plan, item.depot_region),
      amount(item.requested),
      amount(item.available),
      amount(item.unmet),
    ]),
    filename: `allocation-plan-${filePart(plan.planning_date)}-${filePart(plan.plan_id)}.pdf`,
  };
}

export async function downloadAllocationPlanPdf(plan: AllocationPlanResponse): Promise<void> {
  const [{ jsPDF }, autoTableModule] = await Promise.all([
    import("jspdf"),
    import("jspdf-autotable"),
  ]);
  const autoTable = autoTableModule.default;
  const report = buildAllocationReport(plan);
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
  const margin = 40;
  const width = doc.internal.pageSize.getWidth() - margin * 2;
  let cursor = margin;

  doc.setFontSize(14);
  doc.text("HydroFlow resource allocation plan", margin, cursor);
  cursor += 18;
  doc.setFontSize(10);
  doc.text(report.identity, margin, cursor);
  cursor += 14;
  if (report.depots) {
    doc.text(report.depots, margin, cursor);
    cursor += 14;
  }
  doc.text(report.summary, margin, cursor);
  cursor += 14;
  const disclaimerLines = doc.splitTextToSize(report.disclaimer, width) as string[];
  doc.text(disclaimerLines, margin, cursor);
  cursor += disclaimerLines.length * 12 + 8;

  const tableOptions = {
    styles: { fontSize: 8, cellPadding: 4, overflow: "linebreak" as const },
    headStyles: { fillColor: [11, 88, 115] as [number, number, number] },
    showHead: "everyPage" as const,
    margin: { left: margin, right: margin, top: margin, bottom: margin },
  };

  autoTable(doc, {
    ...tableOptions,
    startY: cursor,
    head: [report.townshipHead],
    body: report.townshipBody,
  });

  if (report.itemBody.length) {
    const nextY = (doc as { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? cursor;
    autoTable(doc, {
      ...tableOptions,
      startY: nextY + 18,
      head: [report.itemHead],
      body: report.itemBody,
    });
  }

  if (report.shortageBody.length) {
    const nextY = (doc as { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? cursor;
    autoTable(doc, {
      ...tableOptions,
      startY: nextY + 18,
      head: [report.shortageHead],
      body: report.shortageBody,
      headStyles: { fillColor: [138, 59, 34] },
    });
  }

  doc.save(report.filename);
}

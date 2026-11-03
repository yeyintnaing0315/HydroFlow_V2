import type { AllocationPlanResponse } from "./types";
import { buildSupplyTable } from "./lib/allocationSupplyTable";
import {
  planRouteSummaries,
  selectedRouteLabels,
  summarizePlanResources,
} from "./lib/allocationPrintSummary";

export interface AllocationReport {
  title: string;
  subtitle: string;
  tableHead: string[];
  tableBody: string[][];
  filename: string;
}

function filePart(value: string): string {
  return value.replace(/[^\w.-]+/g, "-");
}

export function buildAllocationReport(plan: AllocationPlanResponse): AllocationReport {
  const table = buildSupplyTable(plan);
  return {
    title: "Resource allocation plan",
    subtitle: `${plan.planning_date} · Plan ${plan.plan_id}${plan.status === "confirmed" ? " · Confirmed" : ""}`,
    tableHead: table.head,
    tableBody: table.body,
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
  const summary = summarizePlanResources(plan);
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
  const margin = 36;
  const pageWidth = doc.internal.pageSize.getWidth();
  let cursor = margin;

  doc.setFontSize(14);
  doc.text(report.title, margin, cursor);
  cursor += 16;
  doc.setFontSize(10);
  doc.text(report.subtitle, margin, cursor);
  cursor += 14;
  doc.setFontSize(9);
  const intro = doc.splitTextToSize(
    `Fund allocated: ${summary.fundAllocatedMmk.toLocaleString()} MMK · Other relief units: ${Math.round(summary.otherUnitsAllocated).toLocaleString()} units · People: ${summary.people.toLocaleString()} · Depots: ${summary.depotLabels.join(", ")}`,
    pageWidth - margin * 2,
  ) as string[];
  doc.text(intro, margin, cursor);
  cursor += intro.length * 11 + 4;

  for (const line of planRouteSummaries(plan)) {
    doc.text(`Route group: ${line}`, margin, cursor);
    cursor += 11;
  }
  for (const line of selectedRouteLabels(plan)) {
    doc.text(line, margin, cursor);
    cursor += 11;
  }
  cursor += 4;
  doc.text("Map: use Print preview in the app for the road map.", margin, cursor);
  cursor += 14;

  if (report.tableBody.length) {
    autoTable(doc, {
      startY: cursor,
      head: [report.tableHead],
      body: report.tableBody,
      styles: { fontSize: 7, cellPadding: 2.5, overflow: "linebreak" },
      headStyles: { fillColor: [11, 88, 115], fontSize: 7 },
      margin: { left: margin, right: margin },
      tableWidth: "auto",
    });
  }

  const disclaimerLines = doc.splitTextToSize(plan.disclaimer, pageWidth - margin * 2) as string[];
  const finalY = (doc as { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? cursor;
  doc.text(disclaimerLines, margin, finalY + 16);

  doc.save(report.filename);
}

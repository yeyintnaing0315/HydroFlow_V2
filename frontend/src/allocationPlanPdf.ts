import type { AllocationPlanResponse } from "./types";
import { buildTownshipSlips, type SupplyGroup, type TownshipSlip } from "./lib/allocationSupplyTable";
import {
  planRouteSummaries,
  selectedRouteLabels,
  summarizePlanResources,
} from "./lib/allocationPrintSummary";

export interface AllocationReport {
  title: string;
  subtitle: string;
  slips: TownshipSlip[];
  filename: string;
}

function filePart(value: string): string {
  return value.replace(/[^\w.-]+/g, "-");
}

export function buildAllocationReport(plan: AllocationPlanResponse): AllocationReport {
  return {
    title: "Resource allocation plan",
    subtitle: `${plan.planning_date} · Plan ${plan.plan_id}${plan.status === "confirmed" ? " · Confirmed" : ""}`,
    slips: buildTownshipSlips(plan),
    filename: `allocation-plan-${filePart(plan.planning_date)}-${filePart(plan.plan_id)}.pdf`,
  };
}

function drawGroups(
  doc: import("jspdf").jsPDF,
  groups: SupplyGroup[],
  x: number,
  y: number,
  width: number,
): number {
  let cursor = y;
  for (const group of groups) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(70, 88, 108);
    doc.text(group.title, x, cursor);
    cursor += 14;
    doc.setFont("helvetica", "normal");
    doc.setTextColor(28, 40, 51);
    doc.setFontSize(11);
    for (const line of group.lines) {
      doc.text(line.name, x, cursor);
      doc.text(line.detail, x + width, cursor, { align: "right" });
      cursor += 15;
    }
    cursor += 8;
  }
  return cursor;
}

export async function downloadAllocationPlanPdf(plan: AllocationPlanResponse): Promise<void> {
  const { jsPDF } = await import("jspdf");
  const report = buildAllocationReport(plan);
  const summary = summarizePlanResources(plan);
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
  const margin = 36;
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  let cursor = margin;

  doc.setTextColor(28, 40, 51);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.text(report.title, margin, cursor);
  cursor += 16;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.text(report.subtitle, margin, cursor);
  cursor += 14;
  doc.setFontSize(10);
  const intro = doc.splitTextToSize(
    `Fund ${summary.fundAllocatedMmk.toLocaleString()} MMK · Relief items ${Math.round(summary.otherUnitsAllocated).toLocaleString()} · People ${summary.people.toLocaleString()} · ${summary.depotLabels.join(", ")}`,
    pageWidth - margin * 2,
  ) as string[];
  doc.text(intro, margin, cursor);
  cursor += intro.length * 13 + 6;

  for (const line of planRouteSummaries(plan)) {
    doc.text(line, margin, cursor);
    cursor += 13;
  }
  for (const line of selectedRouteLabels(plan)) {
    doc.text(line, margin, cursor);
    cursor += 13;
  }
  cursor += 8;

  const columnGap = 28;
  const columnWidth = (pageWidth - margin * 2 - columnGap) / 2;
  for (const slip of report.slips) {
    const blockHeight = 36 + Math.max(
      slip.groups.filter((group) => group.column === "left").reduce((sum, group) => sum + 14 + group.lines.length * 15 + 8, 0),
      slip.groups.filter((group) => group.column === "right").reduce((sum, group) => sum + 14 + group.lines.length * 15 + 8, 0),
    );
    if (cursor + blockHeight > pageHeight - margin) {
      doc.addPage();
      cursor = margin;
    }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13);
    doc.setTextColor(28, 40, 51);
    doc.text(slip.townshipName, margin, cursor);
    cursor += 16;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(11);
    doc.text(
      `Male ${slip.male}     Female ${slip.female}     People ${slip.people}     Fund ${slip.fund}`,
      margin,
      cursor,
    );
    cursor += 20;
    const leftEnd = drawGroups(
      doc,
      slip.groups.filter((group) => group.column === "left"),
      margin,
      cursor,
      columnWidth,
    );
    const rightEnd = drawGroups(
      doc,
      slip.groups.filter((group) => group.column === "right"),
      margin + columnWidth + columnGap,
      cursor,
      columnWidth,
    );
    cursor = Math.max(leftEnd, rightEnd) + 8;
  }

  const disclaimerLines = doc.splitTextToSize(plan.disclaimer, pageWidth - margin * 2) as string[];
  if (cursor + disclaimerLines.length * 12 > pageHeight - margin) {
    doc.addPage();
    cursor = margin;
  }
  doc.setFontSize(8);
  doc.setTextColor(90, 104, 120);
  doc.text(disclaimerLines, margin, cursor + 8);

  doc.save(report.filename);
}

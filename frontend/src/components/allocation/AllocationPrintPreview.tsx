import { createPortal } from "react-dom";
import type { AllocationPlanResponse } from "../../types";
import { buildAllocationReport, downloadAllocationPlanPdf } from "../../allocationPlanPdf";

interface AllocationPrintPreviewProps {
  plan: AllocationPlanResponse;
  onClose: () => void;
}

function ReportTable({ label, head, body }: { label: string; head: string[]; body: string[][] }) {
  if (!body.length) return null;
  return (
    <section>
      <h3>{label}</h3>
      <table aria-label={label}>
        <thead>
          <tr>
            {head.map((cell) => (
              <th key={cell}>{cell}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, index) => (
            <tr key={`${label}-${index}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${head[cellIndex]}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function AllocationPrintPreview({ plan, onClose }: AllocationPrintPreviewProps) {
  const report = buildAllocationReport(plan);
  return createPortal(
    <div className="allocation-print-backdrop" role="presentation" onClick={onClose}>
      <div
        className="allocation-print-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="Allocation report"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="allocation-print-actions">
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
        <header>
          <p className="eyebrow">HydroFlow</p>
          <h2>Resource allocation report</h2>
          <p>{report.identity}</p>
          {report.depots ? <p>{report.depots}</p> : null}
        </header>
        <p className="allocation-print-summary">{report.summary}</p>
        {plan.unverified_stores?.length ? (
          <p className="allocation-alert">
            Unverified depots: {plan.unverified_stores.map((store) => store.name).join(", ")}
          </p>
        ) : null}
        <ReportTable label="Townships" head={report.townshipHead} body={report.townshipBody} />
        <ReportTable label="Line items" head={report.itemHead} body={report.itemBody} />
        <ReportTable label="Shortages" head={report.shortageHead} body={report.shortageBody} />
        <p className="allocation-print-disclaimer">{report.disclaimer}</p>
      </div>
    </div>,
    document.body,
  );
}

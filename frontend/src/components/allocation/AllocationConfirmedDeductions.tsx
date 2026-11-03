import type { PlanDeductionLine } from "../../lib/allocationPlanDeductions";

interface AllocationConfirmedDeductionsProps {
  lines: PlanDeductionLine[];
}

function formatQuantity(value: number, unit: string): string {
  const count = value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return unit === "mmk" ? `${count} ${unit}` : `${count} ${unit}`;
}

export default function AllocationConfirmedDeductions({ lines }: AllocationConfirmedDeductionsProps) {
  if (!lines.length) {
    return (
      <div className="allocation-confirmed-deductions" aria-label="Depot stock reduced">
        <p className="hint allocation-confirmed-deductions-empty">No stock lines were deducted for this plan.</p>
      </div>
    );
  }

  return (
    <div className="allocation-confirmed-deductions" aria-label="Depot stock reduced">
      <p className="allocation-confirmed-deductions-head">Depot stock reduced</p>
      <ul className="allocation-confirmed-deductions-list">
        {lines.map((line) => (
          <li
            key={`${line.category_code}:${line.item_code ?? "fund"}`}
            className="allocation-confirmed-deduction-item"
          >
            <span className="allocation-confirmed-deduction-name">{line.name}</span>
            <span className="allocation-confirmed-deduction-qty">−{formatQuantity(line.allocated, line.unit)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

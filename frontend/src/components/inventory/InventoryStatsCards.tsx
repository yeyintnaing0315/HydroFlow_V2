import { useMemo } from "react";
import { aggregateInventoryStats, toneClassForCategory } from "../../lib/inventoryStats";
import type { InventorySnapshot } from "../../types";
import { ClassGlyph, TotalItemsIcon } from "./InventoryStatGlyphs";

interface InventoryStatsCardsProps {
  snapshots: InventorySnapshot[];
  className?: string;
}

export default function InventoryStatsCards({ snapshots, className }: InventoryStatsCardsProps) {
  const stats = useMemo(() => aggregateInventoryStats(snapshots), [snapshots]);

  const rootClass = ["inv-stats", className].filter(Boolean).join(" ");

  return (
    <section className={rootClass} aria-label="Inventory totals">
      <article className="stat-card tone-total">
        <div>
          <p>
            <span className="stat-icon" aria-hidden="true">
              <TotalItemsIcon />
            </span>
            Total items
          </p>
          <strong>{stats.totalQuantity.toLocaleString()}</strong>
          <small>
            {stats.totalStatus} · {stats.totalFill}%
          </small>
        </div>
      </article>
      {stats.classes.map((row) => (
        <article key={row.code} className={`stat-card ${toneClassForCategory(row.code)}`}>
          <div>
            <p>
              <span className="stat-icon" aria-hidden="true">
                <ClassGlyph classCode={row.code} />
              </span>
              {row.name}
            </p>
            <strong>{row.quantity.toLocaleString()}</strong>
            <small>
              {row.status} · {row.fill}%
            </small>
          </div>
        </article>
      ))}
    </section>
  );
}

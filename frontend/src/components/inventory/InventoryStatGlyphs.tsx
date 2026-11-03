import type { ReactNode } from "react";

function Glyph({ tone, compact, children }: { tone: string; compact?: boolean; children: ReactNode }) {
  return (
    <span className={`item-glyph tone-${tone}${compact ? " is-compact" : ""}`} aria-hidden="true">
      <svg viewBox="0 0 24 24">{children}</svg>
    </span>
  );
}

export function TotalItemsIcon({ compact = false }: { compact?: boolean }) {
  return (
    <Glyph tone="slate" compact={compact}>
      <path d="M4 8h7v7H4zM13 8h7v7h-7zM8 15h7v5H8z" />
    </Glyph>
  );
}

export function ClassGlyph({ classCode, compact = false }: { classCode: string; compact?: boolean }) {
  const tone =
    classCode === "clothing"
      ? "sky"
      : classCode === "foods"
        ? "amber"
        : classCode === "fund"
          ? "green"
          : classCode === "kitchenware"
            ? "rose"
            : "orange";
  return (
    <Glyph tone={tone} compact={compact}>
      {classCode === "clothing" && <path d="M8 7l4-3 4 3v3l3 2-2 2-1-1v7H8V13l-1 1-2-2 3-2V7z" />}
      {classCode === "foods" && <path d="M7 9h10l-1 10H8L7 9zm1-3h8l1 3H7l1-3z" />}
      {classCode === "fund" && <path d="M5 8h14v9H5zM8 8V6h8v2M9 12h6" />}
      {classCode === "kitchenware" && <path d="M6 8h12v8H6zM8 8V6h8v2M10 14h4" />}
      {classCode === "utilities" && <path d="M5 7h14v10H5zM8 7v10M12 7v10M16 7v10" />}
      {classCode !== "clothing" &&
        classCode !== "foods" &&
        classCode !== "fund" &&
        classCode !== "kitchenware" &&
        classCode !== "utilities" && <path d="M5 7h14v10H5zM8 7v10M12 7v10M16 7v10" />}
    </Glyph>
  );
}

import type { ReactNode } from "react";

interface BoardModalProps {
  title: string;
  onClose: () => void;
  page: number;
  pageCount: number;
  onPage: (page: number) => void;
  children: ReactNode;
}

export default function BoardModal({ title, onClose, page, pageCount, onPage, children }: BoardModalProps) {
  return (
    <div
      className="inv-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="inv-modal hf-modal board-modal" role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="board-modal-body">{children}</div>
        {pageCount > 1 ? (
          <div className="board-pager">
            <button type="button" disabled={page <= 0} onClick={() => onPage(page - 1)}>
              Previous
            </button>
            <span>
              {page + 1} / {pageCount}
            </span>
            <button type="button" disabled={page >= pageCount - 1} onClick={() => onPage(page + 1)}>
              Next
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / size));
}

export function pageSlice<T>(items: T[], page: number, size: number): T[] {
  const start = page * size;
  return items.slice(start, start + size);
}

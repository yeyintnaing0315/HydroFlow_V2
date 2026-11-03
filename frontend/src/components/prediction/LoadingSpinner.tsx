interface LoadingSpinnerProps {
  label?: string;
}

export default function LoadingSpinner({ label = "Loading…" }: LoadingSpinnerProps) {
  return (
    <div className="hf-loading" role="status" aria-live="polite">
      <span className="hf-loading-spinner" aria-hidden="true" />
      <span className="hf-loading-label">{label}</span>
    </div>
  );
}

import type { TimeMode } from "../../lib/dates";

interface TimeRangeNavProps {
  mode: TimeMode;
  onModeChange: (mode: TimeMode) => void;
}

export default function TimeRangeNav({ mode, onModeChange }: TimeRangeNavProps) {
  const buttons: { id: TimeMode; label: string }[] = [
    { id: "past", label: "Previous 7 Days" },
    { id: "today", label: "Today" },
    { id: "future", label: "Next 7 Days" },
  ];
  return (
    <div className="time-range-nav" role="group" aria-label="Prediction time range">
      {buttons.map((button) => (
        <button
          key={button.id}
          type="button"
          className={mode === button.id ? "active" : ""}
          aria-pressed={mode === button.id}
          onClick={() => onModeChange(button.id)}
        >
          {button.label}
        </button>
      ))}
    </div>
  );
}

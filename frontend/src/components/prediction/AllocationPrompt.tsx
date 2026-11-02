import type { PredictionTimelineDay } from "../../types";
import { needsResourceAllocation } from "../../lib/allocationFocus";

interface AllocationPromptProps {
  day: PredictionTimelineDay | undefined;
  townshipName: string;
  onPlanResources: () => void;
}

export default function AllocationPrompt({ day, onPlanResources }: AllocationPromptProps) {
  if (!day) return null;

  const level = day.probability_risk_level ?? "unknown";
  if (needsResourceAllocation(level)) {
    return (
      <div className="allocation-prompt allocate">
        <button type="button" className="allocation-action primary" onClick={onPlanResources}>
          Plan resource allocation
        </button>
      </div>
    );
  }

  return (
    <div className="allocation-prompt calm" role="status">
      <p>
        <strong>No allocation needed.</strong>
      </p>
    </div>
  );
}

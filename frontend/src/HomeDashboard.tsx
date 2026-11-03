import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import HomeAllocationRouteMap from "./components/allocation/HomeAllocationRouteMap";
import InventoryStatsCards from "./components/inventory/InventoryStatsCards";
import FloodPredictionNowPanel from "./components/prediction/FloodPredictionNowPanel";
import { riskLabel } from "./components/prediction/mapUtils";
import { PageControls, ViewDialog } from "./components/ViewDialog";
import type { AllocationFocus } from "./lib/allocationFocus";
import { preferredTownshipId } from "./lib/preferredTownship";
import { fillRatio, itemCapacity, statusFor, statusSlug, type StockStatus } from "./lib/stockStatus";
import type {
  AllocationPlanHistoryItem,
  AllocationPlanResponse,
  AssistancePriority,
  BagoAreasResponse,
  InventorySnapshot,
  LoadState,
  PageId,
} from "./types";

interface Resource<T> {
  state: LoadState;
  data?: T;
  error?: string;
}

interface HomeDashboardProps {
  areas: Resource<BagoAreasResponse>;
  onOpenPage: (page: PageId) => void;
  onPlanResources: (focus: AllocationFocus) => void;
}

interface StockLine {
  key: string;
  name: string;
  quantity: number;
  unit: string;
  status: StockStatus;
  fill: number;
  depot: string;
}

const LEVEL_RANK: Record<string, number> = {
  unknown: 0,
  none: 0,
  low: 1,
  moderate: 2,
  high: 3,
  severe: 4,
  very_high: 4,
};

const loading = <T,>(): Resource<T> => ({ state: "loading" });

type HomeInventoryDepot = "both" | "east" | "west";

function inventoryDepotLabel(choice: HomeInventoryDepot): string {
  if (choice === "east") return "Bago East";
  if (choice === "west") return "Bago West";
  return "Bago East & Bago West";
}

function filterSnapshotsByDepot(
  snapshots: InventorySnapshot[],
  choice: HomeInventoryDepot,
): InventorySnapshot[] {
  if (choice === "both") return snapshots;
  return snapshots.filter((snapshot) => snapshot.region === choice);
}

function localDate(): string {
  const day = new Date();
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Unexpected request failure";
}

function formatNumber(value: number, digits = 0): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function newestPlan(plans: AllocationPlanHistoryItem[]): AllocationPlanHistoryItem | undefined {
  return [...plans].sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
}

function levelRank(level: string | null | undefined): number {
  return LEVEL_RANK[level ?? "unknown"] ?? 0;
}

function stockLines(locations: InventorySnapshot[]): StockLine[] {
  return locations.flatMap((snapshot) =>
    snapshot.classes.flatMap((row) =>
      row.items.map((item) => {
        const capacity = itemCapacity(row.code, item);
        return {
          key: `${snapshot.region}:${row.code}:${item.code ?? item.name}`,
          name: item.name,
          quantity: item.quantity,
          unit: item.unit,
          status: statusFor(item.quantity, capacity),
          fill: fillRatio(item.quantity, capacity),
          depot: snapshot.location,
        };
      }),
    ),
  );
}

function byNeed(left: StockLine, right: StockLine): number {
  return left.fill - right.fill || left.name.localeCompare(right.name);
}

function priorityLabel(priority: AssistancePriority): string {
  if (priority === "none") return "None";
  return riskLabel(priority);
}

export default function HomeDashboard({ areas, onOpenPage, onPlanResources }: HomeDashboardProps) {
  const [plan, setPlan] = useState<Resource<AllocationPlanResponse>>(loading);
  const [inventory, setInventory] = useState<Resource<InventorySnapshot[]>>(loading);
  const [homeList, setHomeList] = useState<null | "plan">(null);
  const [homePage, setHomePage] = useState(0);
  const [homeTownship, setHomeTownship] = useState("");
  const [inventoryDepot, setInventoryDepot] = useState<HomeInventoryDepot>("both");
  const asOf = useMemo(() => localDate(), []);

  useEffect(() => {
    if (areas.data && !homeTownship) {
      setHomeTownship(preferredTownshipId(areas.data.districts));
    }
  }, [areas.data, homeTownship]);

  useEffect(() => {
    let active = true;
    api
      .allocationPlans()
      .then(async (plans) => {
        if (!active) return;
        const latest = newestPlan(plans);
        if (!latest) {
          setPlan({ state: "empty" });
          return;
        }
        try {
          const detail = await api.allocationPlanDetail(latest.plan_id);
          if (active) setPlan({ state: "ready", data: detail });
        } catch (reason: unknown) {
          if (active) setPlan({ state: "error", error: errorText(reason) });
        }
      })
      .catch((reason: unknown) => {
        if (active) setPlan({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    api
      .inventoryLocations()
      .then((data) => {
        if (active) setInventory({ state: data.locations.length ? "ready" : "empty", data: data.locations });
      })
      .catch((reason: unknown) => {
        if (active) setInventory({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, []);

  const inventorySnapshots = useMemo(
    () => filterSnapshotsByDepot(inventory.data ?? [], inventoryDepot),
    [inventory.data, inventoryDepot],
  );
  const lines = useMemo(() => stockLines(inventorySnapshots), [inventorySnapshots]);
  const inventoryLines = useMemo(() => [...lines].sort(byNeed), [lines]);

  const allocationRowsAll = [...(plan.data?.rows ?? [])]
    .sort((left, right) => levelRank(right.priority) - levelRank(left.priority) || left.township_name.localeCompare(right.township_name));

  return (
    <main className="home-board">
      <div className="home-columns">
        <article className="panel home-column">
          <div className="section-heading">
            <h2>Flood Prediction</h2>
            <button type="button" className="text-link" onClick={() => onOpenPage("prediction")}>
              Open flood prediction
            </button>
          </div>
          {areas.state === "error" && (
            <p className="state error">Area data could not be loaded. {areas.error}</p>
          )}
          <FloodPredictionNowPanel
            embedded
            className="home-flood-panel"
            areas={areas}
            selectedTownship={homeTownship}
            onSelectTownship={setHomeTownship}
            onPlanResources={onPlanResources}
            onPredictionDetails={() => onOpenPage("prediction")}
          />
        </article>

        <article className="panel home-column home-allocation-column">
          <div className="section-heading">
            <h2>Resource Allocation</h2>
            <button type="button" className="text-link" onClick={() => onOpenPage("allocation")}>
              Open resource allocation
            </button>
          </div>
          {plan.state === "loading" && <p className="state">Loading the latest plan…</p>}
          {plan.state === "error" && <p className="state error">The latest plan could not be loaded. {plan.error}</p>}
          {plan.state === "empty" && (
            <p className="state">No allocation plan yet. Create one from Resource Allocation.</p>
          )}
          {areas.state === "ready" && (
            <HomeAllocationRouteMap areas={areas} inventory={inventory} planningDate={asOf} />
          )}
          {plan.state === "ready" && plan.data && allocationRowsAll.length > 4 ? (
            <button type="button" className="text-link" onClick={() => { setHomePage(0); setHomeList("plan"); }}>
              View plan
            </button>
          ) : null}
        </article>

        <article className="panel home-column home-inventory-column">
          <div className="section-heading">
            <h2>Inventory Management</h2>
            <button type="button" className="text-link" onClick={() => onOpenPage("inventory")}>
              Open inventory
            </button>
          </div>
          {inventory.state === "loading" && <p className="state">Loading stock…</p>}
          {inventory.state === "error" && (
            <p className="state error">Inventory could not be loaded. {inventory.error}</p>
          )}
          {(inventory.state === "ready" || inventory.state === "empty") && (
            <div className="home-inventory-stack">
              <div className="home-inventory-depot-bar">
                <div className="chip-row home-inventory-depot-chips" role="group" aria-label="Inventory depot">
                  <button
                    type="button"
                    className={inventoryDepot === "both" ? "active" : ""}
                    aria-pressed={inventoryDepot === "both"}
                    onClick={() => setInventoryDepot("both")}
                  >
                    Both depots
                  </button>
                  <button
                    type="button"
                    className={inventoryDepot === "east" ? "active" : ""}
                    aria-pressed={inventoryDepot === "east"}
                    onClick={() => setInventoryDepot("east")}
                  >
                    Bago East
                  </button>
                  <button
                    type="button"
                    className={inventoryDepot === "west" ? "active" : ""}
                    aria-pressed={inventoryDepot === "west"}
                    onClick={() => setInventoryDepot("west")}
                  >
                    Bago West
                  </button>
                </div>
                <p className="hint home-inventory-depot-scope">
                  Showing inventory for <strong>{inventoryDepotLabel(inventoryDepot)}</strong>
                </p>
              </div>
              <InventoryStatsCards className="home-inventory-stats" snapshots={inventorySnapshots} />
              {inventoryLines.length === 0 ? (
                <p className="state">No inventory items yet.</p>
              ) : (
                <ul className="home-inventory-items" aria-label="Inventory items">
                  {inventoryLines.map((line) => (
                    <li key={line.key} className="home-inventory-card">
                      <div className="home-inventory-card-head">
                        <strong>{line.name}</strong>
                        <span className={`stock-pill stock-${statusSlug(line.status)}`}>{line.status}</span>
                      </div>
                      <p className="home-inventory-card-meta">
                        {formatNumber(line.quantity)} {line.unit} · {line.depot}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </article>
      </div>

      <ViewDialog title="Allocation plan" open={homeList === "plan"} onClose={() => setHomeList(null)}>
        <ul className="home-list">
          {allocationRowsAll.slice(homePage * 6, homePage * 6 + 6).map((row) => (
            <li key={row.township_id}>
              <strong>{row.township_name}</strong>
              <span>{priorityLabel(row.priority)}</span>
            </li>
          ))}
        </ul>
        <PageControls
          page={homePage}
          pages={Math.max(1, Math.ceil(allocationRowsAll.length / 6))}
          onPage={setHomePage}
        />
      </ViewDialog>
    </main>
  );
}

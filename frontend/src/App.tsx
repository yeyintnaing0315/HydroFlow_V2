import { Component, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import FloodPredictionDashboard, { type PredictionMapContext } from "./FloodPredictionDashboard";
import HomeDashboard from "./HomeDashboard";
import InventoryManagement from "./InventoryManagement";
import ResourceAllocationDashboard from "./ResourceAllocationDashboard";
import type { AllocationFocus } from "./lib/allocationFocus";
import type {
  BagoAreasResponse,
  HealthResponse,
  InundationProduct,
  JobRun,
  LoadState,
  PageId,
  SettlementPoint,
} from "./types";

interface Resource<T> {
  state: LoadState;
  data?: T;
  error?: string;
}

const loading = <T,>(): Resource<T> => ({ state: "loading" });
const errorText = (reason: unknown) =>
  reason instanceof Error ? reason.message : "Unexpected request failure";

const NAV: { id: PageId; label: string }[] = [
  { id: "home", label: "Home" },
  { id: "prediction", label: "Flood Prediction" },
  { id: "allocation", label: "Resource Allocation" },
  { id: "inventory", label: "Inventory Management" },
];

const PAGE_TITLE: Record<PageId, string> = {
  home: "Home",
  prediction: "Flood Prediction",
  allocation: "Resource Allocation",
  inventory: "Inventory Management",
};

function initialStartDate(): string {
  const day = new Date();
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}

function NavIcon({ page }: { page: PageId }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (page === "home") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M4 10.5 12 4l8 6.5" />
        <path {...common} d="M7 10.2V20h10V10.2" />
      </svg>
    );
  }
  if (page === "prediction") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M4 16c2.5-5 4-7 8-7s5.5 2 8 7" />
        <path {...common} d="M4 12c2.5-4 4-5 8-5s5.5 1 8 5" />
      </svg>
    );
  }
  if (page === "allocation") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M12 21s7-4.4 7-10a7 7 0 0 0-14 0c0 5.6 7 10 7 10z" />
        <circle cx="12" cy="11" r="2.2" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...common} d="M3 7.5 12 3l9 4.5-9 4.5L3 7.5z" />
      <path {...common} d="M3 7.5V16.5L12 21l9-4.5V7.5" />
      <path {...common} d="M12 12v9" />
    </svg>
  );
}

class DashboardErrorBoundary extends Component<{ children: ReactNode }, { message: string | null }> {
  state = { message: null as string | null };
  static getDerivedStateFromError(error: Error) {
    return { message: error.message };
  }
  render() {
    if (this.state.message) {
      return (
        <main className="panel">
          <h1>Application stopped</h1>
          <p className="hint">{this.state.message}</p>
        </main>
      );
    }
    return this.props.children;
  }
}

function App() {
  const [health, setHealth] = useState<Resource<HealthResponse>>(loading);
  const [areas, setAreas] = useState<Resource<BagoAreasResponse>>(loading);
  const [runs, setRuns] = useState<Resource<JobRun[]>>(loading);
  const [inundation, setInundation] = useState<Resource<InundationProduct[]>>(loading);
  const [settlements, setSettlements] = useState<Resource<SettlementPoint[]>>(loading);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [, setPredictionMapContext] = useState<PredictionMapContext | null>(null);
  const [startDate, setStartDate] = useState(initialStartDate);
  const [page, setPage] = useState<PageId>("home");
  const [allocationFocus, setAllocationFocus] = useState<AllocationFocus | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      const results = await Promise.allSettled([
        api.health(),
        api.bagoAreas(),
        api.runs(),
        api.inundationProducts(),
        api.settlements(),
      ]);
      if (!active) return;

      const [healthResult, areasResult, runsResult, inundationResult, settlementsResult] = results;
      setHealth(
        healthResult.status === "fulfilled"
          ? { state: "ready", data: healthResult.value }
          : { state: "error", error: errorText(healthResult.reason) },
      );
      setAreas(
        areasResult.status === "fulfilled"
          ? { state: "ready", data: areasResult.value }
          : { state: "error", error: errorText(areasResult.reason) },
      );
      setRuns(
        runsResult.status === "fulfilled"
          ? { state: runsResult.value.length ? "ready" : "empty", data: runsResult.value }
          : { state: "error", error: errorText(runsResult.reason) },
      );
      setInundation(
        inundationResult.status === "fulfilled"
          ? {
              state: inundationResult.value.length ? "ready" : "empty",
              data: inundationResult.value,
            }
          : { state: "error", error: errorText(inundationResult.reason) },
      );
      setSettlements(
        settlementsResult.status === "fulfilled"
          ? {
              state: settlementsResult.value.length ? "ready" : "empty",
              data: settlementsResult.value,
            }
          : { state: "error", error: errorText(settlementsResult.reason) },
      );
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const notices = [
    health.state === "error" ? `API unavailable: ${health.error}` : null,
    health.data && health.data.status !== "ok" ? "API is not reporting a healthy status." : null,
    areas.state === "error" ? "Bago map layers could not be loaded." : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <div className={sidebarOpen ? "shell" : "shell sidebar-closed"}>
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32">
              <path d="M5 20c3.2-4.2 5.2-4.2 8.2 0s5 4.2 8.2 0 5-4.2 8.2 0" />
              <path d="M5 13c3.2-4.2 5.2-4.2 8.2 0s5 4.2 8.2 0" />
            </svg>
          </span>
          <div className="brand-text">
            <strong>
              HydroFlow <em>V2</em>
            </strong>
          </div>
        </div>

        <nav className="sector-nav" aria-label="Primary">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? "active" : ""}
              aria-current={page === item.id ? "page" : undefined}
              onClick={() => setPage(item.id)}
            >
              <NavIcon page={item.id} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className={`status ${health.data?.status === "ok" ? "online" : ""}`}>
            <span aria-hidden="true" />
            API {health.state === "loading" ? "checking" : health.data?.status ?? "unavailable"}
            {health.data && (
              <small>
                {health.data.service} v{health.data.version}
              </small>
            )}
          </div>
        </div>
      </aside>

      <div className={`workspace page-${page} hf-theme`}>
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="icon-btn brand-toggle"
              aria-expanded={sidebarOpen}
              aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
              onClick={() => setSidebarOpen((open) => !open)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 7h16M4 12h16M4 17h16" />
              </svg>
            </button>
            <label className="region-pill">
              <span aria-hidden="true" />
              <select defaultValue="bago" aria-label="Region">
                <option value="bago">Bago Region</option>
              </select>
            </label>
          </div>
          {page === "inventory" && <div id="inventory-search-slot" className="topbar-search" />}

          <div className="top-actions">
            <div className="page-head">
              <h1>{PAGE_TITLE[page]}</h1>
            </div>
            <button
              type="button"
              className="icon-btn notice-btn"
              aria-label="Notifications"
              aria-expanded={noticeOpen}
              onClick={() => setNoticeOpen((open) => !open)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9" />
                <path d="M10 20a2 2 0 0 0 4 0" />
              </svg>
              {notices.length > 0 && <b>{notices.length}</b>}
            </button>
            {noticeOpen && (
              <div className="notice-pop" role="status">
                {notices.length === 0 ? <p>No operational alerts.</p> : notices.map((note) => <p key={note}>{note}</p>)}
              </div>
            )}
          </div>
        </header>

        {page === "home" && (
          <HomeDashboard
            areas={areas}
            onOpenPage={setPage}
            onPlanResources={(focus) => {
              setAllocationFocus(focus);
              setStartDate(focus.date);
              setPage("allocation");
            }}
          />
        )}

        {page === "prediction" && (
          <FloodPredictionDashboard
            areas={areas}
            health={health}
            runs={runs}
            inundation={inundation}
            settlements={settlements}
            onMapContextChange={setPredictionMapContext}
            onPlanResources={(focus) => {
              setAllocationFocus(focus);
              setStartDate(focus.date);
              setPage("allocation");
            }}
          />
        )}

        {page === "allocation" && (
          <ResourceAllocationDashboard
            startDate={startDate}
            onStartDate={setStartDate}
            focus={allocationFocus}
            onClearFocus={() => setAllocationFocus(null)}
            onOpenInventory={() => setPage("inventory")}
            areas={areas}
          />
        )}

        {page === "inventory" && <InventoryManagement />}
      </div>
    </div>
  );
}

export default function HydroFlowApp() {
  return (
    <DashboardErrorBoundary>
      <App />
    </DashboardErrorBoundary>
  );
}

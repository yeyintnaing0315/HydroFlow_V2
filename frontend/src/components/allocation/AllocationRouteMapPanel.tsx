import AllocationOverviewMap, {
  type OverviewDepot,
  type OverviewRoute,
  type OverviewTownship,
} from "./AllocationOverviewMap";

interface AllocationRouteMapPanelProps {
  planningDate: string;
  townshipLabel: string;
  sourceNote?: string | null;
  townships: OverviewTownship[];
  depots: OverviewDepot[];
  routes: OverviewRoute[];
  focusTownshipId?: string | null;
  loadingMessage?: string | null;
  instanceKey: string;
  onSelectTownship?: (townshipId: string) => void;
  routeCaption?: string | null;
  headingLevel?: "h2" | "h3";
  stackClassName?: string;
}

export default function AllocationRouteMapPanel({
  planningDate,
  townshipLabel,
  sourceNote = null,
  townships,
  depots,
  routes,
  focusTownshipId = null,
  loadingMessage = null,
  instanceKey,
  onSelectTownship,
  routeCaption = null,
  headingLevel = "h2",
  stackClassName = "allocation-map-stack",
}: AllocationRouteMapPanelProps) {
  const Title = headingLevel;

  return (
    <div className={stackClassName}>
      <div className="allocation-route-map-head">
        <Title>Route map</Title>
        <div className="allocation-route-map-meta" aria-label="Route map context">
          <span className="allocation-route-map-meta-item">
            <span className="allocation-top-label">Planning date</span>
            <strong>{planningDate}</strong>
          </span>
          <span className="allocation-route-map-meta-item">
            <span className="allocation-top-label">Township</span>
            <strong>{townshipLabel}</strong>
          </span>
        </div>
        {sourceNote ? (
          <span className="source allocation-route-map-source">{sourceNote}</span>
        ) : null}
      </div>
      <AllocationOverviewMap
        instanceKey={instanceKey}
        townships={townships}
        depots={depots}
        routes={routes}
        focusTownshipId={focusTownshipId}
        loadingMessage={loadingMessage}
        onSelectTownship={onSelectTownship}
      />
      <ul className="legend allocation-map-legend" aria-label="Map legend">
        <li>
          <i style={{ background: "#0b5873" }} />
          East depot routes
        </li>
        <li>
          <i style={{ background: "#c45a1a" }} />
          West depot routes
        </li>
        <li>
          <i style={{ background: "#f4b942" }} />
          Bago depot
        </li>
        <li>
          <i style={{ background: "#e07a2f" }} />
          Pyay depot
        </li>
      </ul>
      {routeCaption ? <p className="hint allocation-map-hint">{routeCaption}</p> : null}
    </div>
  );
}

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db, get_inventory_db
from app.schemas.api import (
    AllocationDispatchRequest,
    AllocationPlanRequest,
    DepotNetworkRoutesRequest,
    DepotNetworkRoutesResponse,
    TownshipRouteComparison,
)
from app.services.allocation_network_routes import preview_depot_network_routes
from app.services.allocation import (
    AllocationConfirmResult,
    AllocationNotFound,
    AllocationPlanHistoryItem,
    AllocationPlanView,
    AllocationStateError,
    StoreStatus,
    build_allocation_plan,
    confirm_allocation_plan,
    get_allocation_plan,
    list_allocation_plans,
    list_store_status,
    verify_store,
)
from app.services.route_options import compare_township_routes, select_township_route
from app.services.geography import GeographyUnavailableError
from app.services.inventory import InventoryError, add_region_stock, region_snapshot
from app.services.prediction import ModelUnavailableError

router = APIRouter(prefix="/allocation", tags=["allocation"])


class VerifyStoreBody(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class SelectTownshipRouteBody(BaseModel):
    option_index: int = Field(ge=1, le=3)


@router.get("/stores", response_model=list[StoreStatus])
def read_allocation_stores(
    inventory_session: Session = Depends(get_inventory_db),
) -> list[StoreStatus]:
    payload = list_store_status(inventory_session)
    inventory_session.commit()
    return payload


@router.post("/stores/{region}/verify", response_model=StoreStatus)
def mark_store_verified(
    region: str,
    data: VerifyStoreBody | None = None,
    inventory_session: Session = Depends(get_inventory_db),
) -> StoreStatus:
    try:
        payload = verify_store(inventory_session, region, None if data is None else data.note)
        inventory_session.commit()
    except AllocationStateError as exc:
        inventory_session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.get("/plans", response_model=list[AllocationPlanHistoryItem])
def read_allocation_plans(
    geo_session: Session = Depends(get_db),
) -> list[AllocationPlanHistoryItem]:
    return list_allocation_plans(geo_session)


@router.get("/plans/{plan_id}", response_model=AllocationPlanView)
def read_allocation_plan(
    plan_id: int,
    geo_session: Session = Depends(get_db),
    inventory_session: Session = Depends(get_inventory_db),
) -> AllocationPlanView:
    try:
        return get_allocation_plan(geo_session, inventory_session, plan_id)
    except AllocationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/plans/{plan_id}/townships/{township_id}/routes",
    response_model=TownshipRouteComparison,
)
async def compare_saved_township_routes(
    plan_id: int,
    township_id: str,
    geo_session: Session = Depends(get_db),
) -> TownshipRouteComparison:
    try:
        payload = await compare_township_routes(geo_session, plan_id, township_id)
        geo_session.commit()
    except AllocationNotFound as exc:
        geo_session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AllocationStateError as exc:
        geo_session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        geo_session.rollback()
        raise
    return payload


@router.post(
    "/plans/{plan_id}/townships/{township_id}/routes/select",
    response_model=TownshipRouteComparison,
)
def select_saved_township_route(
    plan_id: int,
    township_id: str,
    data: SelectTownshipRouteBody,
    geo_session: Session = Depends(get_db),
) -> TownshipRouteComparison:
    try:
        payload = select_township_route(geo_session, plan_id, township_id, data.option_index)
        geo_session.commit()
    except AllocationNotFound as exc:
        geo_session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AllocationStateError as exc:
        geo_session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        geo_session.rollback()
        raise
    return payload


@router.post("/network-routes", response_model=DepotNetworkRoutesResponse)
async def read_depot_network_routes(data: DepotNetworkRoutesRequest) -> DepotNetworkRoutesResponse:
    legs = [leg.model_dump() for leg in data.legs]
    routes = await preview_depot_network_routes(legs)
    return DepotNetworkRoutesResponse(routes=routes)


@router.post("/plan", response_model=AllocationPlanView)
async def create_allocation_plan(
    data: AllocationPlanRequest,
    geo_session: Session = Depends(get_db),
    inventory_session: Session = Depends(get_inventory_db),
) -> AllocationPlanView:
    try:
        payload = await build_allocation_plan(geo_session, inventory_session, data)
        geo_session.commit()
        inventory_session.commit()
    except GeographyUnavailableError as exc:
        geo_session.rollback()
        inventory_session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelUnavailableError as exc:
        geo_session.rollback()
        inventory_session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        geo_session.rollback()
        inventory_session.rollback()
        raise
    return payload


@router.post("/plans/{plan_id}/confirm", response_model=AllocationConfirmResult)
def confirm_saved_plan(
    plan_id: int,
    geo_session: Session = Depends(get_db),
    inventory_session: Session = Depends(get_inventory_db),
) -> AllocationConfirmResult:
    try:
        payload = confirm_allocation_plan(geo_session, inventory_session, plan_id)
        inventory_session.commit()
        geo_session.commit()
    except AllocationNotFound as exc:
        inventory_session.rollback()
        geo_session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AllocationStateError, InventoryError) as exc:
        inventory_session.rollback()
        geo_session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        inventory_session.rollback()
        geo_session.rollback()
        raise
    return payload


@router.post("/dispatch")
def confirm_allocation_dispatch(
    data: AllocationDispatchRequest,
    inventory_session: Session = Depends(get_inventory_db),
) -> dict:
    try:
        for line in data.lines:
            add_region_stock(
                inventory_session,
                region=data.warehouse_region,
                category_code=line.category_code,
                item_code=line.item_code,
                quantity=line.quantity,
                entry_mode="manual",
                direction="out",
                note=data.note or line.destination,
            )
        payload = region_snapshot(inventory_session, data.warehouse_region)
        inventory_session.commit()
    except InventoryError as exc:
        inventory_session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload

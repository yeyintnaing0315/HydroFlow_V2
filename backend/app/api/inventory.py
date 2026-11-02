from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_inventory_db
from app.services.detection_store import confirm_detection
from app.services.inventory import (
    InventoryError,
    add_region_stock,
    create_category,
    create_item_type,
    region_snapshot,
)
from app.services.object_detect import ObjectDetectError, detect_image, detect_video

router = APIRouter(tags=["inventory"])


class CatalogCategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    entry_mode: str = Field(pattern="^(scan_or_manual|manual_only)$")
    sort_order: int | None = Field(default=None, ge=1, le=999)


class CatalogItemTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=20)
    sort_order: int | None = Field(default=None, ge=1, le=999)


class InventoryEntry(BaseModel):
    category_code: str = Field(min_length=1, max_length=40)
    item_code: str | None = Field(default=None, max_length=40)
    quantity: float = Field(gt=0)
    entry_mode: str = Field(pattern="^(manual|scan)$")
    direction: str = Field(default="in", pattern="^(in|out)$")
    note: str | None = Field(default=None, max_length=300)


class DetectionConfirmItem(BaseModel):
    item_code: str = Field(min_length=1, max_length=40)
    quantity: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class DetectionConfirmTrack(BaseModel):
    item_code: str = Field(min_length=1, max_length=40)
    track_id: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0, le=1)


class DetectionConfirm(BaseModel):
    category_code: str = Field(min_length=1, max_length=40)
    source: str = Field(pattern="^(image|video)$")
    items: list[DetectionConfirmItem] = Field(min_length=1)
    tracks: list[DetectionConfirmTrack] = Field(default_factory=list)


@router.post("/inventory/detect")
async def detect_inventory_item(
    category_code: str = Form(...),
    image: UploadFile = File(...),
) -> dict:
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=422, detail="Choose a photo.")
    try:
        return detect_image(payload, category_code)
    except ObjectDetectError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/inventory/detect/video")
async def detect_inventory_video(
    category_code: str = Form(...),
    video: UploadFile = File(...),
) -> dict:
    payload = await video.read()
    if not payload:
        raise HTTPException(status_code=422, detail="Choose a video.")
    try:
        return detect_video(payload, category_code)
    except ObjectDetectError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/inventory")
@router.get("/inventory/")
def list_inventory(session: Session = Depends(get_inventory_db)) -> dict:
    try:
        payload = {
            "locations": [
                region_snapshot(session, "east"),
                region_snapshot(session, "west"),
            ]
        }
        session.commit()
    except InventoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.get("/inventory/{region}")
def get_region_inventory(region: str, session: Session = Depends(get_inventory_db)) -> dict:
    try:
        payload = region_snapshot(session, region)
        session.commit()
    except InventoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.post("/inventory/{region}/detections/confirm")
def confirm_inventory_detection(
    region: str,
    body: DetectionConfirm,
    session: Session = Depends(get_inventory_db),
) -> dict:
    """Write the confirmed scan and stock it in. Detect itself does not."""
    try:
        payload = confirm_detection(
            session,
            region=region,
            category_code=body.category_code,
            source=body.source,
            items=[item.model_dump() for item in body.items],
            tracks=[track.model_dump() for track in body.tracks],
        )
        session.commit()
    except (InventoryError, ObjectDetectError) as exc:
        session.rollback()
        status_code = getattr(exc, "status_code", 422)
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return payload


@router.post("/inventory/catalog/categories")
def create_catalog_category(
    body: CatalogCategoryCreate,
    session: Session = Depends(get_inventory_db),
) -> dict:
    try:
        create_category(
            session,
            code=body.code,
            name=body.name,
            entry_mode=body.entry_mode,
            sort_order=body.sort_order,
        )
        payload = {
            "locations": [
                region_snapshot(session, "east"),
                region_snapshot(session, "west"),
            ]
        }
        session.commit()
    except InventoryError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.post("/inventory/catalog/categories/{category_code}/item-types")
def create_catalog_item_type(
    category_code: str,
    body: CatalogItemTypeCreate,
    session: Session = Depends(get_inventory_db),
) -> dict:
    try:
        create_item_type(
            session,
            category_code=category_code,
            code=body.code,
            name=body.name,
            unit=body.unit,
            sort_order=body.sort_order,
        )
        payload = {
            "locations": [
                region_snapshot(session, "east"),
                region_snapshot(session, "west"),
            ]
        }
        session.commit()
    except InventoryError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.post("/inventory/{region}/entries")
def create_region_entry(
    region: str,
    entry: InventoryEntry,
    session: Session = Depends(get_inventory_db),
) -> dict:
    try:
        payload = add_region_stock(
            session,
            region=region,
            category_code=entry.category_code,
            item_code=entry.item_code,
            quantity=entry.quantity,
            entry_mode=entry.entry_mode,
            direction=entry.direction,
            note=entry.note,
        )
        session.commit()
    except InventoryError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload

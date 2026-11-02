"""Save a confirmed detection and the stock receipt that belongs to it.

Unconfirmed detections are not written here and do not change stock. The
inventory page calls this only after the user accepts the counted items.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import DetectionObject, DetectionSession
from app.services.inventory import InventoryError, add_region_stock, load_catalog, store_for_region
from app.services.object_detect import ObjectDetectError, normalize_detect_category


def confirm_detection(
    session: Session,
    *,
    region: str,
    category_code: str,
    source: str,
    items: list[dict[str, object]],
    tracks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Store one confirmed session, its objects, and a stock-in per item.

    The caller commits. A later stock error rolls the session back with the
    movement, so an unconfirmed or rejected scan never remains as stock.
    """
    region = region.strip().lower()
    category_code = normalize_detect_category(category_code.strip().lower())
    source = source.strip().lower()
    if source not in {"image", "video"}:
        raise ObjectDetectError("Detection source must be image or video.")
    _categories, types_by_category = load_catalog(session)
    if category_code not in types_by_category:
        raise ObjectDetectError("Choose clothing, foods, kitchenware, or utilities.")
    parsed_items = _parse_items(items, category_code, types_by_category)
    parsed_tracks = _parse_tracks(tracks or [], category_code, types_by_category)
    if parsed_tracks:
        counts: dict[str, int] = {}
        for track in parsed_tracks:
            counts[track["item_code"]] = counts.get(track["item_code"], 0) + 1
        confirmed = {row["item_code"]: row["quantity"] for row in parsed_items}
        if counts != confirmed:
            raise ObjectDetectError(
                "Each track is counted once, and the confirmed counts must match those tracks."
            )

    store = store_for_region(session, region)
    now = datetime.now(timezone.utc)
    detection = DetectionSession(
        store_id=store.id,
        source=source,
        category_code=category_code,
        created_at=now,
        confirmed_at=now,
    )
    session.add(detection)
    session.flush()

    if parsed_tracks:
        object_rows = [
            DetectionObject(
                session_id=detection.id,
                item_code=track["item_code"],
                quantity=Decimal(1),
                mean_confidence=track["confidence"],
                track_id=track["track_id"],
            )
            for track in parsed_tracks
        ]
    else:
        object_rows = [
            DetectionObject(
                session_id=detection.id,
                item_code=item["item_code"],
                quantity=Decimal(item["quantity"]),
                mean_confidence=item["confidence"],
                track_id=None,
            )
            for item in parsed_items
        ]
    session.add_all(object_rows)
    session.flush()

    snapshot: dict[str, object] | None = None
    for item in parsed_items:
        snapshot = add_region_stock(
            session,
            region=region,
            category_code=category_code,
            item_code=item["item_code"],
            quantity=item["quantity"],
            entry_mode="scan",
            direction="in",
            note="Confirmed detection",
            detection_session_id=detection.id,
        )
    if snapshot is None:
        raise ObjectDetectError("No inventory item was confirmed.")
    return snapshot


def _known_codes(types_by_category: dict[str, list], category_code: str) -> set[str]:
    return {row.code for row in types_by_category.get(category_code, [])}


def _parse_items(
    items: list[dict[str, object]],
    category_code: str,
    types_by_category: dict[str, list],
) -> list[dict[str, object]]:
    if not items:
        raise ObjectDetectError("No inventory item was confirmed.")
    known = _known_codes(types_by_category, category_code)
    parsed: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in items:
        item_code = str(row.get("item_code", "")).strip().lower()
        if item_code not in known:
            raise InventoryError("Choose a subclass of this class")
        if item_code in seen:
            raise ObjectDetectError("Each confirmed item can appear only once.")
        seen.add(item_code)
        parsed.append(
            {
                "item_code": item_code,
                "quantity": _whole_quantity(row.get("quantity")),
                "confidence": _confidence(row.get("confidence")),
            }
        )
    parsed.sort(key=lambda row: str(row["item_code"]))
    return parsed


def _parse_tracks(
    tracks: list[dict[str, object]],
    category_code: str,
    types_by_category: dict[str, list],
) -> list[dict[str, object]]:
    known = _known_codes(types_by_category, category_code)
    deduped: dict[tuple[str, str], float] = {}
    for row in tracks:
        item_code = str(row.get("item_code", "")).strip().lower()
        track_id = str(row.get("track_id", "")).strip()
        if item_code not in known:
            raise InventoryError("Choose a subclass of this class")
        if not track_id:
            raise ObjectDetectError("Each video track needs an id.")
        if len(track_id) > 80:
            raise ObjectDetectError("A track id is too long.")
        key = (item_code, track_id)
        score = _confidence(row.get("confidence"))
        deduped[key] = max(deduped.get(key, 0.0), score)
    parsed = [
        {"item_code": item_code, "track_id": track_id, "confidence": confidence}
        for (item_code, track_id), confidence in deduped.items()
    ]
    parsed.sort(key=lambda row: (str(row["item_code"]), _track_sort(str(row["track_id"]))))
    return parsed


def _whole_quantity(value: object) -> int:
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ObjectDetectError(
            "Detected quantity must be a whole number greater than zero."
        ) from exc
    if amount != amount.to_integral_value() or amount <= 0:
        raise ObjectDetectError("Detected quantity must be a whole number greater than zero.")
    return int(amount)


def _confidence(value: object) -> float:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ObjectDetectError("Confidence must be between 0 and 1.") from exc
    if score < 0 or score > 1:
        raise ObjectDetectError("Confidence must be between 0 and 1.")
    return round(score, 4)


def _track_sort(track_id: str) -> tuple[int, object]:
    return (0, int(track_id)) if track_id.isdigit() else (1, track_id)

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_inventory_db
from app.main import app
from app.models import DetectionObject, DetectionSession, StockMovement, Store
from app.services.detection_store import confirm_detection
from app.services.inventory import add_region_stock, seed_catalog, seed_regions
from app.services.object_detect import (
    CONFIDENCE_MIN,
    Detection,
    ObjectDetectError,
    count_detections,
    count_tracks,
    detect_image,
    detect_video,
    detection_runtime_ready,
    normalize_item_code,
    resolve_category_weights,
    resolve_detection_weights,
)


def test_detection_runtime_ready_reports_import_status() -> None:
    assert isinstance(detection_runtime_ready(), bool)


def test_yolo_class_names_map_to_inventory_item_codes() -> None:
    assert normalize_item_code("dipper") == "water_dipper"
    assert normalize_item_code("can") == "canned_fish"
    assert normalize_item_code("rice") == "rice"


def test_every_confident_subclass_in_one_frame_is_counted() -> None:
    crowded = count_detections(
        [
            Detection("cup", 0.4),
            Detection("cup", 0.5),
            Detection("bowl", 0.99),
            Detection("spoon", 0.1),
        ]
    )
    assert crowded == [
        {"item_code": "cup", "quantity": 2, "confidence": 0.45},
        {"item_code": "bowl", "quantity": 1, "confidence": 0.99},
    ]

    tied = count_detections(
        [
            Detection("cup", 0.4),
            Detection("cup", 0.5),
            Detection("bowl", 0.8),
            Detection("bowl", 0.9),
        ]
    )
    assert tied[0]["item_code"] == "bowl"
    assert tied[0]["quantity"] == 2
    assert tied[0]["confidence"] == pytest.approx(0.85)
    assert tied[1]["item_code"] == "cup"


def test_a_photo_with_no_confident_box_counts_nothing() -> None:
    assert count_detections([Detection("cup", 0.2)]) == []
    assert count_detections([]) == []


def test_resolve_category_weights_prefers_yolo_runs(monkeypatch, tmp_path: Path) -> None:
    yolo = tmp_path / "ml" / "runs" / "yolo" / "repair20_foods" / "weights"
    yolo.mkdir(parents=True)
    yolo_weights = yolo / "best.pt"
    yolo_weights.write_bytes(b"yolo")
    served = tmp_path / "ml" / "models" / "object_detect" / "foods"
    served.mkdir(parents=True)
    (served / "best.pt").write_bytes(b"served")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.services.object_detect.yolo_runs_root",
        lambda: tmp_path / "ml" / "runs" / "yolo",
    )
    monkeypatch.setattr(
        "app.services.object_detect.weights_root",
        lambda: tmp_path / "ml" / "models" / "object_detect",
    )

    assert resolve_category_weights("foods") == yolo_weights


def test_detect_image_counts_boxes_for_the_selected_class(monkeypatch, tmp_path: Path) -> None:
    weights = tmp_path / "kitchenware" / "best.pt"
    weights.parent.mkdir()
    weights.write_bytes(b"stub")
    monkeypatch.setenv("OBJECT_DETECT_WEIGHTS", str(tmp_path))
    monkeypatch.setattr(
        "app.services.object_detect.predict_boxes",
        lambda path, image: [
            Detection("cup", 0.8),
            Detection("cup", 0.6),
            Detection("bowl", 0.95),
        ],
    )

    assert detect_image(b"jpeg-bytes", "utility") == {
        "category_code": "kitchenware",
        "items": [
            {"item_code": "bowl", "quantity": 1, "confidence": 0.95},
        ],
    }


def test_missing_weights_and_unknown_classes_do_not_guess(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OBJECT_DETECT_WEIGHTS", str(tmp_path))
    with pytest.raises(ObjectDetectError, match="not installed") as missing:
        detect_image(b"jpeg-bytes", "clothes")
    assert missing.value.status_code == 503
    with pytest.raises(ObjectDetectError, match="Choose clothing"):
        detect_image(b"jpeg-bytes", "fund")
    with pytest.raises(ObjectDetectError, match="Choose a photo"):
        detect_image(b"", "foods")


def test_detect_route_returns_the_counted_item(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.inventory.detect_image",
        lambda image, category_code: {
            "category_code": category_code,
            "items": [
                {"item_code": "rice", "quantity": 3, "confidence": 0.81},
                {"item_code": "oil", "quantity": 1, "confidence": 0.74},
            ],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/inventory/detect",
        data={"category_code": "foods"},
        files={"image": ("frame.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert response.status_code == 200
    assert response.json() == {
        "category_code": "foods",
        "items": [
            {"item_code": "rice", "quantity": 3, "confidence": 0.81},
            {"item_code": "oil", "quantity": 1, "confidence": 0.74},
        ],
    }


def test_detect_route_rejects_an_empty_photo() -> None:
    client = TestClient(app)
    response = client.post(
        "/inventory/detect",
        data={"category_code": "clothes"},
        files={"image": ("frame.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose a photo."


def test_video_detect_route_returns_tracks(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.inventory.detect_video",
        lambda video, category_code: {
            "category_code": category_code,
            "frames_processed": 32,
            "items": [{"item_code": "cup", "quantity": 2, "confidence": 0.78}],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/inventory/detect/video",
        data={"category_code": "utility"},
        files={"video": ("scan.mp4", b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["item_code"] == "cup"


def test_video_detection_rejects_unknown_class_and_empty_payload() -> None:
    with pytest.raises(ObjectDetectError, match="Choose clothing"):
        detect_video(b"video", "fund")
    with pytest.raises(ObjectDetectError, match="Choose a video"):
        detect_video(b"", "foods")


def test_each_track_id_counts_once_per_class() -> None:
    items, tracks = count_tracks(
        {
            "cup": {1: [0.5, 0.5], 2: [0.9]},
            "rice": {1: [0.99]},
            "bowl": {1: [0.8]},
        },
        known={"cup", "bowl"},
    )
    assert items == [
        {"item_code": "cup", "quantity": 2, "confidence": 0.7},
        {"item_code": "bowl", "quantity": 1, "confidence": 0.8},
    ]
    assert tracks == [
        {"item_code": "bowl", "track_id": "1", "confidence": 0.8},
        {"item_code": "cup", "track_id": "1", "confidence": 0.5},
        {"item_code": "cup", "track_id": "2", "confidence": 0.9},
    ]


def test_v2_weights_replace_category_models_and_still_filter_the_class(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "object_detect"
    category = root / "kitchenware" / "best.pt"
    category.parent.mkdir(parents=True)
    category.write_bytes(b"v8")
    monkeypatch.setenv("OBJECT_DETECT_WEIGHTS", str(root))
    assert resolve_detection_weights("kitchenware") == category
    assert resolve_detection_weights("utility") == category

    promoted = root / "v2" / "best.pt"
    promoted.parent.mkdir()
    promoted.write_bytes(b"yolo11s")
    assert resolve_detection_weights("kitchenware") == promoted
    assert resolve_detection_weights("clothes") == promoted

    def predict(path: Path, image: bytes) -> list[Detection]:
        assert path == promoted
        assert image == b"jpeg-bytes"
        return [Detection("tshirt", 0.91), Detection("rice", 0.99)]

    monkeypatch.setattr("app.services.object_detect.predict_boxes", predict)
    assert detect_image(b"jpeg-bytes", "clothes") == {
        "category_code": "clothing",
        "items": [{"item_code": "tshirt", "quantity": 1, "confidence": 0.91}],
    }

    monkeypatch.setattr(
        "app.services.object_detect.predict_boxes",
        lambda path, image: [Detection("rice", 0.99)],
    )
    with pytest.raises(ObjectDetectError, match="does not stock"):
        detect_image(b"jpeg-bytes", "clothes")


class _Tensor:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


class _Boxes:
    cls = _Tensor([0, 0, 1])
    conf = _Tensor([0.9, 0.4, 0.8])
    id = _Tensor([4, 4, 4])


class _Result:
    names = {0: "cup", 1: "bowl"}
    boxes = _Boxes()


class _Model:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def track(self, **kwargs: object) -> list[_Result]:
        self.calls.append(kwargs)
        return [_Result()]


class _Capture:
    def __init__(self) -> None:
        self.left = 2
        self.released = False

    def read(self) -> tuple[bool, object | None]:
        if self.left <= 0:
            return False, None
        self.left -= 1
        return True, object()

    def release(self) -> None:
        self.released = True


def test_video_bytetrack_uses_v2_weights_and_counts_each_track_once(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "object_detect"
    category = root / "kitchenware" / "best.pt"
    category.parent.mkdir(parents=True)
    category.write_bytes(b"v8")
    promoted = root / "v2" / "best.pt"
    promoted.parent.mkdir()
    promoted.write_bytes(b"yolo11s")
    monkeypatch.setenv("OBJECT_DETECT_WEIGHTS", str(root))

    model = _Model()
    capture = _Capture()
    loaded: dict[str, Path] = {}

    def load(path: Path) -> _Model:
        loaded["path"] = path
        return model

    monkeypatch.setattr("app.services.object_detect._load_model", load)
    monkeypatch.setattr("app.services.object_detect._open_capture", lambda path: capture)

    result = detect_video(b"video-bytes", "utility")

    assert loaded["path"] == promoted

    assert capture.released is True
    assert len(model.calls) == 2
    assert model.calls[0]["tracker"] == "bytetrack.yaml"
    assert model.calls[0]["persist"] is True
    assert model.calls[0]["conf"] == CONFIDENCE_MIN
    assert result == {
        "category_code": "kitchenware",
        "frames_processed": 2,
        "items": [
            {"item_code": "bowl", "quantity": 1, "confidence": 0.8},
            {"item_code": "water_dipper", "quantity": 1, "confidence": 0.65},
        ],
        "tracks": [
            {"item_code": "bowl", "track_id": "4", "confidence": 0.8},
            {"item_code": "water_dipper", "track_id": "4", "confidence": 0.65},
        ],
    }


@pytest.fixture()
def detection_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_catalog(session)
        seed_regions(session)
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


def _quantity(snapshot: dict, category_code: str, item_code: str) -> float:
    klass = next(row for row in snapshot["classes"] if row["code"] == category_code)
    return next(item["quantity"] for item in klass["items"] if item["code"] == item_code)


def test_confirm_stores_the_session_objects_and_stock_movement(detection_session: Session) -> None:
    snapshot = confirm_detection(
        detection_session,
        region="east",
        category_code="kitchenware",
        source="image",
        items=[
            {"item_code": "water_dipper", "quantity": 2, "confidence": 0.7},
            {"item_code": "bowl", "quantity": 1, "confidence": 0.95},
        ],
    )
    detection_session.commit()
    stored = detection_session.scalars(select(DetectionSession)).all()
    assert len(stored) == 1
    assert stored[0].source == "image"
    assert stored[0].category_code == "kitchenware"
    assert stored[0].confirmed_at is not None
    east = detection_session.scalar(select(Store).where(Store.region == "east"))
    assert stored[0].store_id == east.id
    objects = detection_session.scalars(select(DetectionObject).order_by(DetectionObject.item_code)).all()
    assert [(row.item_code, float(row.quantity), row.track_id) for row in objects] == [
        ("bowl", 1.0, None),
        ("water_dipper", 2.0, None),
    ]
    movements = detection_session.scalars(select(StockMovement)).all()
    assert len(movements) == 2
    assert {row.detection_session_id for row in movements} == {stored[0].id}
    assert {row.entry_mode for row in movements} == {"scan"}
    assert {row.direction for row in movements} == {"in"}
    assert _quantity(snapshot, "kitchenware", "water_dipper") == 2
    assert _quantity(snapshot, "kitchenware", "bowl") == 1
    scans = [row for row in snapshot["movements"] if row["entry_mode"] == "scan"]
    assert {row["item_code"] for row in scans} == {"water_dipper", "bowl"}


def test_video_confirm_stores_one_object_per_track(detection_session: Session) -> None:
    snapshot = confirm_detection(
        detection_session,
        region="west",
        category_code="kitchenware",
        source="video",
        items=[{"item_code": "water_dipper", "quantity": 2, "confidence": 0.7}],
        tracks=[
            {"item_code": "water_dipper", "track_id": "9", "confidence": 0.8},
            {"item_code": "water_dipper", "track_id": "8", "confidence": 0.6},
        ],
    )
    objects = detection_session.scalars(select(DetectionObject).order_by(DetectionObject.track_id)).all()
    assert [(row.track_id, float(row.quantity)) for row in objects] == [("8", 1.0), ("9", 1.0)]
    movement = detection_session.scalar(select(StockMovement))
    assert movement is not None
    assert movement.detection_session_id == objects[0].session_id
    assert float(movement.quantity) == 2
    assert _quantity(snapshot, "kitchenware", "water_dipper") == 2


def test_unmatched_tracks_and_detect_calls_do_not_change_stock(
    monkeypatch, detection_session: Session
) -> None:
    with pytest.raises(ObjectDetectError, match="track"):
        confirm_detection(
            detection_session,
            region="east",
            category_code="kitchenware",
            source="video",
            items=[{"item_code": "water_dipper", "quantity": 2, "confidence": 0.5}],
            tracks=[{"item_code": "water_dipper", "track_id": "1", "confidence": 0.5}],
        )
    monkeypatch.setattr(
        "app.api.inventory.detect_image",
        lambda image, category_code: {
            "category_code": category_code,
            "items": [{"item_code": "rice", "quantity": 3, "confidence": 0.8}],
        },
    )
    monkeypatch.setattr(
        "app.api.inventory.detect_video",
        lambda video, category_code: {
            "category_code": category_code,
            "frames_processed": 2,
            "items": [{"item_code": "cup", "quantity": 1, "confidence": 0.5}],
            "tracks": [{"item_code": "cup", "track_id": "1", "confidence": 0.5}],
        },
    )
    app.dependency_overrides[get_inventory_db] = lambda: detection_session
    try:
        client = TestClient(app)
        image = client.post(
            "/inventory/detect",
            data={"category_code": "foods"},
            files={"image": ("frame.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
        )
        video = client.post(
            "/inventory/detect/video",
            data={"category_code": "utility"},
            files={"video": ("scan.mp4", b"video-bytes", "video/mp4")},
        )
        assert image.status_code == 200
        assert video.status_code == 200
        assert detection_session.scalars(select(DetectionSession)).all() == []
        assert detection_session.scalars(select(StockMovement)).all() == []
    finally:
        app.dependency_overrides.pop(get_inventory_db, None)


def test_confirm_route_rolls_back_when_stock_is_full(detection_session: Session) -> None:
    add_region_stock(
        detection_session,
        region="east",
        category_code="kitchenware",
        item_code="water_dipper",
        quantity=20000,
        entry_mode="manual",
    )
    detection_session.commit()
    app.dependency_overrides[get_inventory_db] = lambda: detection_session
    try:
        client = TestClient(app)
        response = client.post(
            "/inventory/east/detections/confirm",
            json={
                "category_code": "kitchenware",
                "source": "image",
                "items": [{"item_code": "water_dipper", "quantity": 1, "confidence": 0.9}],
            },
        )
        assert response.status_code == 422
        assert "limited to 20000" in response.json()["detail"]
        assert detection_session.scalars(select(DetectionSession)).all() == []
        balance = _quantity(
            client.get("/inventory/east").json(),
            "kitchenware",
            "water_dipper",
        )
        assert balance == 20000
    finally:
        app.dependency_overrides.pop(get_inventory_db, None)


def test_confirm_route_returns_scan_movements(detection_session: Session) -> None:
    app.dependency_overrides[get_inventory_db] = lambda: detection_session
    try:
        client = TestClient(app)
        response = client.post(
            "/inventory/east/detections/confirm",
            json={
                "category_code": "foods",
                "source": "video",
                "items": [{"item_code": "oil", "quantity": 1, "confidence": 0.66}],
                "tracks": [{"item_code": "oil", "track_id": "3", "confidence": 0.66}],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert _quantity(body, "foods", "oil") == 1
        assert any(row["entry_mode"] == "scan" and row["item_code"] == "oil" for row in body["movements"])
        west = client.get("/inventory/west")
        assert west.status_code == 200
        assert _quantity(west.json(), "foods", "oil") == 0
        stored = detection_session.scalars(select(DetectionObject)).one()
        assert stored.track_id == "3"
        assert float(stored.quantity) == 1
    finally:
        app.dependency_overrides.pop(get_inventory_db, None)

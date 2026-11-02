"""Count inventory items in a photo or a short video.

When ml/models/object_detect/v2/best.pt is present, every class uses that
single YOLO11s model. Until then, each scannable class uses its own weights
under ml/models/object_detect/<class>/best.pt (YOLOv8m exports from
model_training for clothing, foods, kitchenware, and utilities). Fund has
no photos and is not detected. One photo or
video can contain several subclasses. Stock is unchanged here; the page
saves the counts only after the user confirms.
"""

from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.services.inventory import ITEM_TYPES

CONFIDENCE_MIN = 0.35
MAX_IMAGE_BYTES = 12_000_000
MAX_VIDEO_BYTES = 200_000_000
MAX_VIDEO_FRAMES = 900
DETECTABLE = tuple(ITEM_TYPES.keys())
_LEGACY_DETECT_CATEGORY = {
    "clothes": "clothing",
    "utility": "kitchenware",
}
# YOLO name strings that differ from inventory item codes in the catalog.
_ITEM_CODE_ALIASES: dict[str, str] = {
    "can": "canned_fish",
    "dipper": "water_dipper",
    "cup": "water_dipper",
}


_RUNTIME_HINT = (
    "Install detection dependencies in the project venv, then restart the API: "
    "pip install opencv-python-headless ultralytics (see backend/README.md)."
)


class ObjectDetectError(Exception):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def detection_runtime_ready() -> bool:
    """True when OpenCV and Ultralytics are importable in this Python environment."""
    try:
        import cv2  # noqa: F401
        from ultralytics import YOLO  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True)
class Detection:
    item_code: str
    confidence: float


def weights_root() -> Path:
    override = os.environ.get("OBJECT_DETECT_WEIGHTS")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "ml" / "models"
        if candidate.is_dir():
            return candidate / "object_detect"
    return here.parents[3] / "ml" / "models" / "object_detect"


def yolo_runs_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "ml" / "runs" / "yolo"
        if candidate.is_dir():
            return candidate
    return here.parents[3] / "ml" / "runs" / "yolo"


def v2_weights_file() -> Path:
    """The single YOLO11s export. Absent until Colab training is copied in."""
    return weights_root() / "v2" / "best.pt"


def resolve_category_weights(category_code: str) -> Path:
    """Prefer trained runs under ml/runs/yolo, then promoted ml/models weights."""
    category_code = normalize_detect_category(category_code.strip().lower())
    folder = category_code
    override = os.environ.get("OBJECT_DETECT_WEIGHTS")
    if override:
        return Path(override) / folder / "best.pt"
    for run_name in (f"repair20_{folder}", f"epoch20_{folder}"):
        candidate = yolo_runs_root() / run_name / "weights" / "best.pt"
        if candidate.is_file():
            return candidate
    return weights_root() / folder / "best.pt"


def normalize_detect_category(category_code: str) -> str:
    code = category_code.strip().lower()
    return _LEGACY_DETECT_CATEGORY.get(code, code)


def normalize_item_code(label: str) -> str:
    cleaned = label.strip().lower()
    return _ITEM_CODE_ALIASES.get(cleaned, cleaned)


def resolve_detection_weights(category_code: str) -> Path:
    """Use the single v2 model when it exists, otherwise the category weights file."""
    category_code = normalize_detect_category(category_code.strip().lower())
    promoted = v2_weights_file()
    if promoted.is_file():
        return promoted
    return resolve_category_weights(category_code)


def count_detections(
    boxes: list[Detection],
    *,
    minimum: float = CONFIDENCE_MIN,
    known: set[str] | None = None,
) -> list[dict[str, object]]:
    """Count every subclass in one frame. Larger counts are listed first."""
    grouped: dict[str, list[float]] = defaultdict(list)
    for box in boxes:
        if box.confidence < minimum:
            continue
        if known is not None and box.item_code not in known:
            continue
        grouped[box.item_code].append(box.confidence)
    items = [
        {
            "item_code": item_code,
            "quantity": len(scores),
            "confidence": round(sum(scores) / len(scores), 4),
        }
        for item_code, scores in grouped.items()
    ]
    items.sort(
        key=lambda item: (
            -int(item["quantity"]),
            -float(item["confidence"]),
            str(item["item_code"]),
        )
    )
    return items


def count_tracks(
    tracks: dict[str, dict[int, list[float]]],
    *,
    known: set[str] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Count each track id once per class.

    The same numeric id on two classes is two items. Repeated frames of one
    id do not increase the count. Returns the confirm list and one row per track.
    """
    items: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for label, track_scores in tracks.items():
        if known is not None and label not in known:
            continue
        means: list[float] = []
        for track_id in sorted(track_scores):
            scores = track_scores[track_id]
            if not scores:
                continue
            mean = sum(scores) / len(scores)
            means.append(mean)
            rows.append(
                {
                    "item_code": label,
                    "track_id": str(track_id),
                    "confidence": round(mean, 4),
                }
            )
        if not means:
            continue
        items.append(
            {
                "item_code": label,
                "quantity": len(means),
                "confidence": round(sum(means) / len(means), 4),
            }
        )
    items.sort(
        key=lambda item: (
            -int(item["quantity"]),
            -float(item["confidence"]),
            str(item["item_code"]),
        )
    )
    rows.sort(key=lambda row: (str(row["item_code"]), _track_sort(str(row["track_id"]))))
    return items, rows


def _track_sort(track_id: str) -> tuple[int, object]:
    return (0, int(track_id)) if track_id.isdigit() else (1, track_id)


def _decode_image(image: bytes):
    """Decode an uploaded image into the ndarray Ultralytics expects."""
    try:
        import cv2
        import numpy as np

        decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    except ImportError as exc:
        raise ObjectDetectError(
            f"The detection runtime is not installed. {_RUNTIME_HINT}",
            status_code=503,
        ) from exc
    if decoded is None:
        raise ObjectDetectError("That photo could not be read.")
    return decoded


def predict_boxes(weights: Path, image: bytes) -> list[Detection]:
    """Run one detector. Ultralytics is imported here so other tests stay light."""
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ObjectDetectError(
            f"The detection runtime is not installed. {_RUNTIME_HINT}",
            status_code=503,
        ) from exc

    model = _load_model(weights)
    try:
        results = model.predict(source=_decode_image(image), conf=CONFIDENCE_MIN, verbose=False)
    except ObjectDetectError:
        raise
    except Exception as exc:
        raise ObjectDetectError("That photo could not be read.") from exc
    if not results:
        return []
    result = results[0]
    names = result.names or {}
    found = getattr(result, "boxes", None)
    if found is None or found.cls is None:
        return []
    boxes: list[Detection] = []
    for class_id, confidence in zip(found.cls.tolist(), found.conf.tolist(), strict=True):
        raw = names.get(int(class_id), "")
        if raw:
            boxes.append(Detection(normalize_item_code(str(raw)), float(confidence)))
    return boxes


# Cache models, but reload automatically when a promoted best.pt changes.
_MODELS: dict[str, tuple[int, object]] = {}


def _load_model(weights: Path) -> object:
    key = str(weights.resolve())
    modified_at = weights.stat().st_mtime_ns
    cached = _MODELS.get(key)
    if cached is None or cached[0] != modified_at:
        from ultralytics import YOLO

        model = YOLO(key)
        _MODELS[key] = (modified_at, model)
        return model
    return cached[1]


def _open_capture(path: str):
    """Open a video. The frame loop then tracks objects with ByteTrack."""
    try:
        import cv2
    except ImportError as exc:
        raise ObjectDetectError(
            "The video detection runtime is not installed.",
            status_code=503,
        ) from exc
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise ObjectDetectError("That video could not be read.")
    return capture


def detect_image(image: bytes, category_code: str) -> dict[str, object]:
    category_code = normalize_detect_category(category_code.strip().lower())
    if category_code not in DETECTABLE:
        raise ObjectDetectError("Choose clothing, foods, kitchenware, or utilities.")
    if not image:
        raise ObjectDetectError("Choose a photo.")
    if len(image) > MAX_IMAGE_BYTES:
        raise ObjectDetectError("That photo is too large.")
    weights = resolve_detection_weights(category_code)
    if not weights.is_file():
        raise ObjectDetectError(
            "The detection model for this class is not installed.",
            status_code=503,
        )
    known = {code for code, *_rest in ITEM_TYPES[category_code]}
    boxes = predict_boxes(weights, image)
    items = count_detections(boxes, known=known)
    if not items:
        confident = [box for box in boxes if box.confidence >= CONFIDENCE_MIN]
        if confident:
            raise ObjectDetectError("The model returned an item this class does not stock.")
        raise ObjectDetectError("No inventory item was found in this photo.")
    return {"category_code": category_code, "items": items}


def detect_video(video: bytes, category_code: str) -> dict[str, object]:
    """Track items across a short video and count each track only once.

    The returned count is a review aid, never a stock update. Stock changes
    only when the user confirms, which stores the session and the receipt.
    """
    category_code = normalize_detect_category(category_code.strip().lower())
    if category_code not in DETECTABLE:
        raise ObjectDetectError("Choose clothing, foods, kitchenware, or utilities.")
    if not video:
        raise ObjectDetectError("Choose a video.")
    if len(video) > MAX_VIDEO_BYTES:
        raise ObjectDetectError("That video is too large. Maximum size is 200 MB.")

    weights = resolve_detection_weights(category_code)
    if not weights.is_file():
        raise ObjectDetectError("The detection model for this class is not installed.", status_code=503)

    temp_name = ""
    frames = 0
    tracks: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as source:
            source.write(video)
            temp_name = source.name
        capture = _open_capture(temp_name)
        try:
            model = _load_model(weights)
            while frames < MAX_VIDEO_FRAMES:
                ok, frame = capture.read()
                if not ok:
                    break
                frames += 1
                results = model.track(
                    source=frame,
                    conf=CONFIDENCE_MIN,
                    persist=True,
                    tracker="bytetrack.yaml",
                    verbose=False,
                )
                if not results:
                    continue
                boxes = getattr(results[0], "boxes", None)
                if boxes is None or boxes.id is None or boxes.cls is None:
                    continue
                names = results[0].names or {}
                for class_id, confidence, track_id in zip(
                    boxes.cls.tolist(), boxes.conf.tolist(), boxes.id.tolist(), strict=True
                ):
                    raw = str(names.get(int(class_id), ""))
                    if raw:
                        label = normalize_item_code(raw)
                        tracks[label][int(track_id)].append(float(confidence))
        finally:
            capture.release()
    except ObjectDetectError:
        raise
    except Exception as exc:
        raise ObjectDetectError("That video could not be processed.") from exc
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)

    if not frames:
        raise ObjectDetectError("That video has no readable frames.")
    known = {code for code, *_rest in ITEM_TYPES[category_code]}
    items, track_rows = count_tracks(tracks, known=known)
    if not items:
        raise ObjectDetectError("No inventory item was found in this video.")
    return {
        "category_code": category_code,
        "frames_processed": frames,
        "items": items,
        "tracks": track_rows,
    }

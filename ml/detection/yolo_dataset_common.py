"""Shared helpers for HydroFlow YOLOv8 dataset builders."""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

try:
    import albumentations as A
except ImportError as exc:
    raise SystemExit("Install albumentations: pip install albumentations") from exc

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif", ".tif", ".tiff"}

SPLIT_RATIOS = {"train": 0.8, "valid": 0.1, "test": 0.1}
SOURCE_SPLIT_RATIOS = {"train": 0.70, "valid": 0.15, "test": 0.15}


def read_image_bgr(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path))
    if image is not None:
        return image
    try:
        with Image.open(path) as pil:
            rgb = pil.convert("RGB")
            array = np.array(rgb)
            return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    except OSError:
        return None


@dataclass(frozen=True)
class RawSourceRecord:
    path: Path
    class_name: str
    class_id: int
    split: str
    bbox_xywh: tuple[int, int, int, int]
    area_ratio: float
    flagged: bool


@dataclass(frozen=True)
class LabeledSourceRecord:
    path: Path
    class_name: str
    class_id: int
    split: str
    yolo_boxes: tuple[tuple[float, float, float, float], ...]


def load_bbox_overrides(out_dir: Path) -> dict[str, list[float]]:
    override_path = out_dir / "meta" / "bbox_overrides.json"
    if not override_path.is_file():
        return {}
    data = json.loads(override_path.read_text(encoding="utf-8"))
    return {str(k): list(v) for k, v in data.items()}


def foreground_mask(image_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    best_mask: np.ndarray | None = None
    best_area = 0.0
    for thresh in (252, 248, 244, 240):
        _, mask = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        area = float(max(cv2.contourArea(c) for c in contours))
        if area > best_area:
            best_area = area
            best_mask = mask
    if best_mask is None:
        best_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.rectangle(best_mask, (w // 8, h // 8), (7 * w // 8, 7 * h // 8), 255, -1)
    return best_mask


def mask_to_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        h, w = mask.shape
        return w // 8, h // 8, 3 * w // 4, 3 * h // 4
    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())
    return x1, y1, x2 - x1 + 1, y2 - y1 + 1


def xywh_to_yolo(
    x: int, y: int, w: int, h: int, img_w: int, img_h: int
) -> tuple[float, float, float, float]:
    cx = (x + w / 2) / img_w
    cy = (y + h / 2) / img_h
    return cx, cy, w / img_w, h / img_h


def yolo_to_xywh(
    cx: float, cy: float, bw: float, bh: float, img_w: int, img_h: int
) -> tuple[int, int, int, int]:
    w = int(bw * img_w)
    h = int(bh * img_h)
    x = int(cx * img_w - w / 2)
    y = int(cy * img_h - h / 2)
    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))
    w = max(1, min(w, img_w - x))
    h = max(1, min(h, img_h - y))
    return x, y, w, h


def detect_bbox(
    image_bgr: np.ndarray,
    overrides: dict[str, list[float]],
    source_key: str,
) -> tuple[tuple[int, int, int, int], float, bool]:
    h, w = image_bgr.shape[:2]
    if source_key in overrides:
        cx, cy, bw, bh = overrides[source_key]
        box = yolo_to_xywh(cx, cy, bw, bh, w, h)
        area_ratio = (box[2] * box[3]) / (w * h)
        return box, area_ratio, False
    mask = foreground_mask(image_bgr)
    box = mask_to_bbox(mask)
    area_ratio = (box[2] * box[3]) / (w * h)
    flagged = area_ratio < 0.05
    return box, area_ratio, flagged


def assign_source_splits(keys: list, rng: random.Random) -> dict:
    shuffled = list(keys)
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train = max(1, int(round(n * SOURCE_SPLIT_RATIOS["train"])))
    n_valid = max(1, int(round(n * SOURCE_SPLIT_RATIOS["valid"])))
    if n_train + n_valid >= n:
        n_train = max(1, n - 2)
        n_valid = 1 if n > 1 else 0
    n_test = max(0, n - n_train - n_valid)
    if n >= 3 and n_test == 0:
        n_train -= 1
        n_test = 1
    split_map = {}
    for key in shuffled[:n_train]:
        split_map[key] = "train"
    for key in shuffled[n_train : n_train + n_valid]:
        split_map[key] = "valid"
    for key in shuffled[n_train + n_valid :]:
        split_map[key] = "test"
    return split_map


def split_aug_budget(total: int, splits: list[str]) -> dict[str, int]:
    counts = {s: int(total * SPLIT_RATIOS[s]) for s in splits}
    remainder = total - sum(counts.values())
    for s in splits:
        if remainder <= 0:
            break
        counts[s] += 1
        remainder -= 1
    return counts


def distribute_per_source(total: int, n_sources: int) -> list[int]:
    if n_sources == 0:
        return []
    base, rem = divmod(total, n_sources)
    return [base + (1 if i < rem else 0) for i in range(n_sources)]


def random_background(size: int, rng: random.Random) -> np.ndarray:
    kind = rng.choice(["solid", "gradient", "noise", "tiles"])
    if kind == "solid":
        color = np.array(
            [rng.randint(40, 220), rng.randint(40, 220), rng.randint(40, 220)],
            dtype=np.uint8,
        )
        bg = np.full((size, size, 3), color, dtype=np.uint8)
    elif kind == "gradient":
        c1 = np.array([rng.randint(30, 200)] * 3, dtype=np.float32)
        c2 = np.array([rng.randint(30, 200)] * 3, dtype=np.float32)
        t = np.linspace(0, 1, size, dtype=np.float32)[:, None]
        row = (c1 * (1 - t) + c2 * t).astype(np.uint8)
        bg = np.tile(row, (size, 1, 1))
    elif kind == "noise":
        bg = np.random.default_rng(rng.randint(0, 2**31)).integers(
            60, 201, (size, size, 3), dtype=np.uint8
        )
        bg = cv2.GaussianBlur(bg, (9, 9), 0)
    else:
        bg = np.full((size, size, 3), 200, dtype=np.uint8)
        step = rng.choice([32, 48, 64])
        for y in range(0, size, step):
            for x in range(0, size, step):
                shade = rng.randint(120, 230)
                cv2.rectangle(bg, (x, y), (min(x + step, size), min(y + step, size)), (shade,) * 3, -1)
    return bg


def paste_on_background(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    bbox: tuple[int, int, int, int],
    size: int,
    rng: random.Random,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    x, y, w, h = bbox
    fg = image_bgr[y : y + h, x : x + w]
    fg_mask = mask[y : y + h, x : x + w]
    if fg.size == 0:
        fg = image_bgr
        fg_mask = mask

    scale = rng.uniform(0.55, 0.92)
    target_h = int(size * scale)
    aspect = fg.shape[1] / max(fg.shape[0], 1)
    target_w = int(target_h * aspect)
    target_w = max(24, min(target_w, size - 8))
    target_h = max(24, min(target_h, size - 8))
    fg_resized = cv2.resize(fg, (target_w, target_h), interpolation=cv2.INTER_AREA)
    mask_resized = cv2.resize(fg_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

    bg = random_background(size, rng)
    max_x = size - target_w - 1
    max_y = size - target_h - 1
    px = rng.randint(0, max(0, max_x))
    py = rng.randint(0, max(0, max_y))

    alpha = (mask_resized.astype(np.float32) / 255.0)[..., None]
    roi = bg[py : py + target_h, px : px + target_w].astype(np.float32)
    blended = alpha * fg_resized.astype(np.float32) + (1 - alpha) * roi
    bg[py : py + target_h, px : px + target_w] = blended.astype(np.uint8)

    cx = (px + target_w / 2) / size
    cy = (py + target_h / 2) / size
    return bg, (cx, cy, target_w / size, target_h / size)


def build_augment_pipeline(rng_seed: int) -> A.Compose:
    return A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.Rotate(limit=15, border_mode=cv2.BORDER_CONSTANT, fill=(255, 255, 255), p=0.6),
            A.RandomBrightnessContrast(brightness_limit=0.25, contrast_limit=0.25, p=0.7),
            A.HueSaturationValue(hue_shift_limit=8, sat_shift_limit=25, val_shift_limit=20, p=0.5),
            A.GaussNoise(std_range=(0.02, 0.08), p=0.35),
            A.MotionBlur(blur_limit=5, p=0.2),
            A.ImageCompression(quality_range=(75, 95), p=0.3),
        ],
        bbox_params=A.BboxParams(format="yolo", label_fields=["class_labels"], min_visibility=0.35),
        seed=rng_seed,
    )


def write_label(path: Path, class_id: int, yolo_box: tuple[float, float, float, float]) -> None:
    cx, cy, bw, bh = yolo_box
    path.write_text(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n", encoding="utf-8")


def write_multi_label(
    path: Path,
    boxes: list[tuple[int, tuple[float, float, float, float]]],
) -> None:
    lines = []
    for class_id, (cx, cy, bw, bh) in boxes:
        lines.append(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def draw_qa_overlay(
    image_bgr: np.ndarray,
    class_names: list[str],
    class_id: int,
    yolo_box: tuple[float, float, float, float],
) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    x, y, bw, bh = yolo_to_xywh(*yolo_box, w, h)
    out = image_bgr.copy()
    cv2.rectangle(out, (x, y), (x + bw, y + bh), (0, 200, 0), 2)
    label = class_names[class_id] if class_id < len(class_names) else str(class_id)
    cv2.putText(
        out,
        label,
        (x, max(20, y - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 160, 0),
        2,
    )
    return out


def _clear_glob_dir(directory: Path, pattern: str) -> None:
    if not directory.is_dir():
        return
    for path in directory.glob(pattern):
        try:
            path.unlink()
        except OSError:
            pass


def prepare_output_dirs(out_dir: Path, clean: bool) -> None:
    for split in ("train", "valid", "test"):
        img_dir = out_dir / split / "images"
        lbl_dir = out_dir / split / "labels"
        if clean:
            _clear_glob_dir(img_dir, "*")
            _clear_glob_dir(lbl_dir, "*")
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = out_dir / "meta" / "qa"
    if clean:
        _clear_glob_dir(qa_dir, "*.jpg")
        manifest = out_dir / "meta" / "source_manifest.csv"
        if manifest.is_file():
            manifest.unlink(missing_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)


def write_data_yaml(out_dir: Path, names: list[str]) -> None:
    names_str = ", ".join(names)
    content = (
        "path: .\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        f"nc: {len(names)}\n"
        f"names: [{names_str}]\n"
    )
    (out_dir / "data.yaml").write_text(content, encoding="utf-8")


def write_manifest(out_dir: Path, manifest_rows: list[dict[str, object]]) -> None:
    if not manifest_rows:
        return
    manifest_path = out_dir / "meta" / "source_manifest.csv"
    fieldnames = list(manifest_rows[0].keys())
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)


def print_summary(out_dir: Path, per_class: int, class_names: list[str]) -> None:
    for split in ("train", "valid", "test"):
        n_img = len(list((out_dir / split / "images").glob("*.jpg")))
        n_lbl = len(list((out_dir / split / "labels").glob("*.txt")))
        print(f"{split}: {n_img} images, {n_lbl} labels")
    total = sum(len(list((out_dir / s / "images").glob("*.jpg"))) for s in ("train", "valid", "test"))
    print(f"total images: {total} (target {per_class * len(class_names)})")
    print(f"data.yaml: {out_dir / 'data.yaml'}")


def augment_raw_source(
    rec: RawSourceRecord,
    *,
    count: int,
    imgsz: int,
    rng: random.Random,
    out_dir: Path,
    raw_dir: Path,
    manifest_rows: list[dict[str, object]],
    qa_pool: list[tuple[np.ndarray, int, tuple[float, float, float, float]]],
    qa_pool_limit: int,
) -> None:
    image = read_image_bgr(rec.path)
    if image is None:
        return
    mask = foreground_mask(image)
    ih, iw = image.shape[:2]

    for aug_idx in range(count):
        use_paste = rng.random() < 0.45
        if use_paste:
            out_img, yolo_box = paste_on_background(image, mask, rec.bbox_xywh, imgsz, rng)
        else:
            pipeline = build_augment_pipeline(rng.randint(0, 2**31 - 1))
            resized = cv2.resize(image, (imgsz, imgsz), interpolation=cv2.INTER_AREA)
            sx, sy = imgsz / iw, imgsz / ih
            rx, ry, rw, rh = rec.bbox_xywh
            yolo_on_resized = xywh_to_yolo(
                int(rx * sx), int(ry * sy), int(rw * sx), int(rh * sy), imgsz, imgsz
            )
            try:
                out = pipeline(
                    image=resized,
                    bboxes=[yolo_on_resized],
                    class_labels=[rec.class_id],
                )
                out_img = out["image"]
                yolo_box = tuple(out["bboxes"][0])
            except Exception:
                out_img = resized
                yolo_box = yolo_on_resized

        stem = f"{rec.class_name}_{rec.path.stem}_aug{aug_idx:04d}"
        img_path = out_dir / rec.split / "images" / f"{stem}.jpg"
        lbl_path = out_dir / rec.split / "labels" / f"{stem}.txt"
        cv2.imwrite(str(img_path), out_img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        write_label(lbl_path, rec.class_id, yolo_box)

        manifest_rows.append(
            {
                "output_image": str(img_path.relative_to(out_dir)),
                "source": str(rec.path.relative_to(raw_dir)),
                "class": rec.class_name,
                "class_id": rec.class_id,
                "split": rec.split,
                "aug_index": aug_idx,
                "used_background_paste": use_paste,
                "source_bbox_xywh": rec.bbox_xywh,
                "source_area_ratio": round(rec.area_ratio, 4),
                "source_flagged": rec.flagged,
            }
        )
        if len(qa_pool) < qa_pool_limit:
            qa_pool.append((out_img, rec.class_id, yolo_box))


def augment_labeled_source(
    rec: LabeledSourceRecord,
    *,
    count: int,
    imgsz: int,
    rng: random.Random,
    out_dir: Path,
    source_key: str,
    manifest_rows: list[dict[str, object]],
    qa_pool: list[tuple[np.ndarray, int, tuple[float, float, float, float]]],
    qa_pool_limit: int,
) -> None:
    image = read_image_bgr(rec.path)
    if image is None or not rec.yolo_boxes:
        return
    ih, iw = image.shape[:2]
    boxes = list(rec.yolo_boxes)
    class_labels = [rec.class_id] * len(boxes)

    for aug_idx in range(count):
        pipeline = build_augment_pipeline(rng.randint(0, 2**31 - 1))
        resized = cv2.resize(image, (imgsz, imgsz), interpolation=cv2.INTER_AREA)
        sx, sy = imgsz / iw, imgsz / ih
        scaled_boxes = []
        for cx, cy, bw, bh in boxes:
            x, y, w, h = yolo_to_xywh(cx, cy, bw, bh, iw, ih)
            scaled_boxes.append(
                xywh_to_yolo(int(x * sx), int(y * sy), int(w * sx), int(h * sy), imgsz, imgsz)
            )
        try:
            out = pipeline(
                image=resized,
                bboxes=scaled_boxes,
                class_labels=class_labels,
            )
            out_img = out["image"]
            out_boxes = out["bboxes"]
        except Exception:
            out_img = resized
            out_boxes = scaled_boxes

        stem = f"{rec.class_name}_{rec.path.stem}_aug{aug_idx:04d}"
        img_path = out_dir / rec.split / "images" / f"{stem}.jpg"
        lbl_path = out_dir / rec.split / "labels" / f"{stem}.txt"
        cv2.imwrite(str(img_path), out_img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        write_multi_label(
            lbl_path,
            [(rec.class_id, tuple(box)) for box in out_boxes],
        )

        manifest_rows.append(
            {
                "output_image": str(img_path.relative_to(out_dir)),
                "source": source_key,
                "class": rec.class_name,
                "class_id": rec.class_id,
                "split": rec.split,
                "aug_index": aug_idx,
                "used_background_paste": False,
                "source_bbox_xywh": "",
                "source_area_ratio": "",
                "source_flagged": False,
            }
        )
        if len(qa_pool) < qa_pool_limit and out_boxes:
            qa_pool.append((out_img, rec.class_id, tuple(out_boxes[0])))


def save_qa_overlays(
    out_dir: Path,
    class_names: list[str],
    qa_pool: dict[str, list[tuple[np.ndarray, int, tuple[float, float, float, float]]]],
    qa_per_class: int,
    rng: random.Random,
) -> None:
    for class_name in class_names:
        picks = qa_pool.get(class_name, [])
        rng.shuffle(picks)
        for idx, (img, class_id, yolo_box) in enumerate(picks[:qa_per_class]):
            overlay = draw_qa_overlay(img, class_names, class_id, yolo_box)
            cv2.imwrite(str(out_dir / "meta" / "qa" / f"{class_name}_{idx:02d}.jpg"), overlay)

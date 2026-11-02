"""Build kitchenware YOLOv8 dataset from data/inventory/Raw/Kitchenware."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import yolo_dataset_common as common

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = ROOT / "data" / "inventory" / "Raw" / "Kitchenware"
DEFAULT_OUT = ROOT / "data" / "processed" / "object_detect" / "kitchenware"

YOLO_NAMES = ["plate", "pot", "soap", "dipper", "mug", "bowl", "knife", "spoon"]
NAME_TO_ID = {name: idx for idx, name in enumerate(YOLO_NAMES)}

RAW_FOLDERS: dict[str, str] = {
    "plate": "plate",
    "pot": "pot",
    "soap": "soap",
    "water dipper": "dipper",
}

ROBOFLOW_DATASETS: dict[str, tuple[str, int | None]] = {
    "mug-real100-3d100.v2i.yolov8": ("mug", None),
    "Bowl.v1i.yolov8": ("bowl", None),
    "Knife.v1i.yolov8": ("knife", None),
    "short spoon fork spoon.v1i.yolov8": ("spoon", 2),
}


def parse_yolo_label_file(
    label_path: Path,
    *,
    keep_class_index: int | None,
) -> list[tuple[float, float, float, float]]:
    if not label_path.is_file():
        return []
    boxes: list[tuple[float, float, float, float]] = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        src_cls = int(float(parts[0]))
        if keep_class_index is not None and src_cls != keep_class_index:
            continue
        if len(parts) == 5:
            boxes.append(
                (float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]))
            )
            continue
        coords = [float(v) for v in parts[1:]]
        if len(coords) < 6 or len(coords) % 2 != 0:
            continue
        xs = coords[0::2]
        ys = coords[1::2]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        boxes.append(((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1))
    return boxes


def collect_raw_sources(
    raw_dir: Path,
    overrides: dict[str, list[float]],
) -> list[common.RawSourceRecord]:
    records: list[common.RawSourceRecord] = []
    for folder, class_name in RAW_FOLDERS.items():
        class_id = NAME_TO_ID[class_name]
        class_dir = raw_dir / folder
        if not class_dir.is_dir():
            raise SystemExit(f"Missing folder: {class_dir}")
        images = sorted(p for p in class_dir.iterdir() if p.suffix.lower() in common.IMAGE_SUFFIXES)
        if not images:
            raise SystemExit(f"No images in {class_dir}")
        rng = random.Random(100 + class_id)
        split_map = common.assign_source_splits(images, rng)
        for path in images:
            image = common.read_image_bgr(path)
            if image is None:
                raise SystemExit(f"Could not read: {path}")
            key = str(path.relative_to(raw_dir)).replace("\\", "/")
            bbox, area_ratio, flagged = common.detect_bbox(image, overrides, key)
            records.append(
                common.RawSourceRecord(
                    path=path,
                    class_name=class_name,
                    class_id=class_id,
                    split=split_map[path],
                    bbox_xywh=bbox,
                    area_ratio=area_ratio,
                    flagged=flagged,
                )
            )
    return records


def collect_labeled_sources(raw_dir: Path) -> list[common.LabeledSourceRecord]:
    records: list[common.LabeledSourceRecord] = []
    for dataset_dir, (class_name, keep_idx) in ROBOFLOW_DATASETS.items():
        class_id = NAME_TO_ID[class_name]
        base = raw_dir / dataset_dir
        if not base.is_dir():
            raise SystemExit(f"Missing dataset: {base}")
        pairs: list[tuple[Path, Path, str]] = []
        for split in ("train", "valid", "test"):
            img_dir = base / split / "images"
            lbl_dir = base / split / "labels"
            if not img_dir.is_dir():
                continue
            for img_path in sorted(img_dir.iterdir()):
                if img_path.suffix.lower() not in common.IMAGE_SUFFIXES:
                    continue
                lbl_path = lbl_dir / f"{img_path.stem}.txt"
                source_key = f"{dataset_dir}/{split}/{img_path.name}"
                pairs.append((img_path, lbl_path, source_key))

        rng = random.Random(200 + class_id)
        split_map = common.assign_source_splits([key for _, _, key in pairs], rng)
        key_to_pair = {key: (img, lbl) for img, lbl, key in pairs}

        for source_key, split in split_map.items():
            img_path, lbl_path = key_to_pair[source_key]
            boxes = parse_yolo_label_file(lbl_path, keep_class_index=keep_idx)
            if not boxes:
                continue
            records.append(
                common.LabeledSourceRecord(
                    path=img_path,
                    class_name=class_name,
                    class_id=class_id,
                    split=split,
                    yolo_boxes=tuple(boxes),
                )
            )
    return records


def generate_dataset(
    raw_dir: Path,
    out_dir: Path,
    *,
    per_class: int,
    imgsz: int,
    seed: int,
    clean: bool,
    qa_per_class: int,
) -> None:
    overrides = common.load_bbox_overrides(out_dir)
    raw_sources = collect_raw_sources(raw_dir, overrides)
    labeled_sources = collect_labeled_sources(raw_dir)
    common.prepare_output_dirs(out_dir, clean)

    rng = random.Random(seed)
    by_class_raw: dict[str, list[common.RawSourceRecord]] = {n: [] for n in YOLO_NAMES}
    by_class_labeled: dict[str, list[common.LabeledSourceRecord]] = {n: [] for n in YOLO_NAMES}
    for rec in raw_sources:
        by_class_raw[rec.class_name].append(rec)
    for rec in labeled_sources:
        by_class_labeled[rec.class_name].append(rec)

    manifest_rows: list[dict[str, object]] = []
    qa_pool: dict[str, list] = {n: [] for n in YOLO_NAMES}

    for class_name in YOLO_NAMES:
        class_sources = by_class_raw[class_name] + by_class_labeled[class_name]
        split_budget = common.split_aug_budget(per_class, list(common.SPLIT_RATIOS.keys()))
        for split_name, budget in split_budget.items():
            raw_split = [r for r in by_class_raw[class_name] if r.split == split_name]
            lbl_split = [r for r in by_class_labeled[class_name] if r.split == split_name]
            combined = len(raw_split) + len(lbl_split)
            per_source_counts = common.distribute_per_source(budget, combined)
            raw_counts = per_source_counts[: len(raw_split)]
            lbl_counts = per_source_counts[len(raw_split) :]

            for rec, count in zip(raw_split, raw_counts):
                if count <= 0:
                    continue
                common.augment_raw_source(
                    rec,
                    count=count,
                    imgsz=imgsz,
                    rng=rng,
                    out_dir=out_dir,
                    raw_dir=raw_dir,
                    manifest_rows=manifest_rows,
                    qa_pool=qa_pool[class_name],
                    qa_pool_limit=qa_per_class * 3,
                )
            for rec, count in zip(lbl_split, lbl_counts):
                if count <= 0:
                    continue
                source_key = str(rec.path.relative_to(raw_dir)).replace("\\", "/")
                common.augment_labeled_source(
                    rec,
                    count=count,
                    imgsz=imgsz,
                    rng=rng,
                    out_dir=out_dir,
                    source_key=source_key,
                    manifest_rows=manifest_rows,
                    qa_pool=qa_pool[class_name],
                    qa_pool_limit=qa_per_class * 3,
                )

        for rec in by_class_raw[class_name]:
            manifest_rows.append(
                {
                    "output_image": "",
                    "source": str(rec.path.relative_to(raw_dir)),
                    "class": class_name,
                    "class_id": rec.class_id,
                    "split": rec.split,
                    "aug_index": -1,
                    "used_background_paste": False,
                    "source_bbox_xywh": rec.bbox_xywh,
                    "source_area_ratio": round(rec.area_ratio, 4),
                    "source_flagged": rec.flagged,
                }
            )
        for rec in by_class_labeled[class_name]:
            manifest_rows.append(
                {
                    "output_image": "",
                    "source": str(rec.path.relative_to(raw_dir)),
                    "class": class_name,
                    "class_id": rec.class_id,
                    "split": rec.split,
                    "aug_index": -1,
                    "used_background_paste": False,
                    "source_bbox_xywh": "",
                    "source_area_ratio": "",
                    "source_flagged": False,
                }
            )

    common.write_manifest(out_dir, manifest_rows)
    common.save_qa_overlays(out_dir, YOLO_NAMES, qa_pool, qa_per_class, rng)
    common.write_data_yaml(out_dir, YOLO_NAMES)
    common.print_summary(out_dir, per_class, YOLO_NAMES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build kitchenware YOLOv8 dataset.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--per-class", type=int, default=1000)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--qa-per-class", type=int, default=30)
    args = parser.parse_args()
    generate_dataset(
        args.raw_dir.resolve(),
        args.out_dir.resolve(),
        per_class=args.per_class,
        imgsz=args.imgsz,
        seed=args.seed,
        clean=args.clean,
        qa_per_class=args.qa_per_class,
    )


if __name__ == "__main__":
    main()

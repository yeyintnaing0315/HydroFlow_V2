"""Build a YOLOv8 foods dataset from raw studio photos under data/inventory/Raw/Foods."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import yolo_dataset_common as common

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = ROOT / "data" / "inventory" / "Raw" / "Foods"
DEFAULT_OUT = ROOT / "data" / "processed" / "object_detect" / "foods"

CLASS_FOLDERS: dict[str, tuple[str, int]] = {
    "rice": ("rice", 0),
    "oil": ("oil", 1),
    "canned_fish": ("canned_fish", 2),
}
YOLO_NAMES = ["rice", "oil", "canned_fish"]


def collect_sources(raw_dir: Path, overrides: dict[str, list[float]]) -> list[common.RawSourceRecord]:
    records: list[common.RawSourceRecord] = []
    for folder, (class_name, class_id) in CLASS_FOLDERS.items():
        class_dir = raw_dir / folder
        if not class_dir.is_dir():
            raise SystemExit(f"Missing class folder: {class_dir}")
        images = sorted(
            p for p in class_dir.iterdir() if p.suffix.lower() in common.IMAGE_SUFFIXES
        )
        if not images:
            raise SystemExit(f"No images in {class_dir}")
        rng = random.Random(42 + class_id)
        split_map = common.assign_source_splits(images, rng)
        for path in images:
            image = common.read_image_bgr(path)
            if image is None:
                raise SystemExit(f"Could not read image: {path}")
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
    sources = collect_sources(raw_dir, overrides)
    common.prepare_output_dirs(out_dir, clean)

    rng = random.Random(seed)
    by_class: dict[str, list[common.RawSourceRecord]] = {name: [] for name in YOLO_NAMES}
    for rec in sources:
        by_class[rec.class_name].append(rec)

    manifest_rows: list[dict[str, object]] = []
    qa_pool: dict[str, list] = {n: [] for n in YOLO_NAMES}

    for class_name in YOLO_NAMES:
        class_sources = by_class[class_name]
        split_budget = common.split_aug_budget(per_class, list(common.SPLIT_RATIOS.keys()))
        for split_name, budget in split_budget.items():
            split_sources = [r for r in class_sources if r.split == split_name]
            per_source_counts = common.distribute_per_source(budget, len(split_sources))
            for rec, count in zip(split_sources, per_source_counts):
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

        for rec in class_sources:
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

    common.write_manifest(out_dir, manifest_rows)
    common.save_qa_overlays(out_dir, YOLO_NAMES, qa_pool, qa_per_class, rng)
    common.write_data_yaml(out_dir, YOLO_NAMES)
    common.print_summary(out_dir, per_class, YOLO_NAMES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build foods YOLOv8 dataset with augmentation.")
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

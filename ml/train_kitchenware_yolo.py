"""Train the kitchenware YOLO detector from the terminal.

Build the dataset first:

    python ml/detection/build_kitchenware_yolo_dataset.py --clean

Train (GPU example):

    python ml/train_kitchenware_yolo.py --weights yolov8m.pt --device 0 --batch 4 --promote

Writes:
  - Run artifacts: ml/runs/yolo/run_kitchenware/
  - Per-epoch metrics: ml/runs/yolo/run_kitchenware/results.csv
  - Copied history: ml/models/object_detect/kitchenware/training_history.csv
  - Weights (with --promote): ml/models/object_detect/kitchenware/best.pt
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path

from train_object_detect import RUNS, ROOT, train_one

DATASET_DIR = ROOT / "data" / "processed" / "object_detect" / "kitchenware"
SERVED_DIR = ROOT / "ml" / "models" / "object_detect" / "kitchenware"
DEFAULT_RUN_NAME = "run_kitchenware"

# Inventory scan expects water_dipper; the dataset builder uses dipper in labels.
_DIPPER_NAME = re.compile(r"\bdipper\b")


@dataclass(frozen=True)
class TrainKitchenwareResult:
    best_weights: Path
    run_dir: Path
    history_csv: Path
    served_history: Path
    epochs_logged: int


def ensure_catalog_class_names(data_yaml: Path) -> None:
    """Rewrite data.yaml names so YOLO class ids match inventory item codes."""
    text = data_yaml.read_text(encoding="utf-8")
    if "water_dipper" in text:
        return
    updated = _DIPPER_NAME.sub("water_dipper", text)
    if updated != text:
        data_yaml.write_text(updated, encoding="utf-8")
        print(f"updated {data_yaml} (dipper -> water_dipper in names)")


def summarize_history(csv_path: Path, *, tail: int = 5) -> None:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print(f"training history empty: {csv_path}")
        return
    columns = ["epoch", "train/box_loss", "metrics/mAP50(B)", "metrics/mAP50-95(B)"]
    present = [c for c in columns if c in rows[0]]
    print(f"training history: {csv_path} ({len(rows)} epochs)")
    print(",".join(present))
    for row in rows[-tail:]:
        print(",".join(row.get(c, "") for c in present))


def train_kitchenware(
    *,
    weights: Path,
    epochs: int,
    imgsz: int,
    patience: int,
    device: str | int,
    batch: int,
    promote: bool,
    run_name: str = DEFAULT_RUN_NAME,
    run_root: Path = RUNS,
) -> TrainKitchenwareResult:
    data_yaml = DATASET_DIR / "data.yaml"
    if not data_yaml.is_file():
        raise SystemExit(
            f"Missing kitchenware dataset: {data_yaml}\n"
            "Run: python ml/detection/build_kitchenware_yolo_dataset.py --clean"
        )
    ensure_catalog_class_names(data_yaml)

    best = train_one(
        "kitchenware",
        run_name=run_name,
        run_root=run_root,
        promote=promote,
        weights=weights,
        epochs=epochs,
        imgsz=imgsz,
        patience=patience,
        device=device,
        batch=batch,
    )

    run_dir = run_root / run_name
    served_history = SERVED_DIR / "training_history.csv"
    with served_history.open(newline="", encoding="utf-8") as handle:
        epochs_logged = sum(1 for _ in csv.DictReader(handle))

    return TrainKitchenwareResult(
        best_weights=best,
        run_dir=run_dir,
        history_csv=run_dir / "results.csv",
        served_history=served_history,
        epochs_logged=epochs_logged,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train kitchenware YOLOv8 and export training_history.csv.")
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "yolov8m.pt",
        help="Starter checkpoint (default yolov8m.pt).",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--batch", type=int, default=4, help="Use 4 on RTX 3050 4GB with yolov8m.")
    parser.add_argument(
        "--device",
        default="0",
        help="cpu, 0, cuda, etc. (default 0 for first GPU).",
    )
    parser.add_argument("--promote", action="store_true", help="Copy best.pt into ml/models/object_detect/kitchenware/.")
    parser.add_argument("--run-name", default=DEFAULT_RUN_NAME)
    parser.add_argument("--run-root", type=Path, default=RUNS)
    args = parser.parse_args()

    device: str | int = int(args.device) if str(args.device).isdigit() else args.device
    weights = args.weights if args.weights.is_file() else Path(str(args.weights))

    result = train_kitchenware(
        weights=weights,
        epochs=args.epochs,
        imgsz=args.imgsz,
        patience=args.patience,
        device=device,
        batch=args.batch,
        promote=args.promote,
        run_name=args.run_name,
        run_root=args.run_root,
    )

    print(f"best weights: {result.best_weights}")
    print(f"run directory: {result.run_dir}")
    summarize_history(result.served_history)


if __name__ == "__main__":
    main()

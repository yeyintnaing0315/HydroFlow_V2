"""Train kitchenware YOLOv8m on GPU (terminal). Saves training_history.csv.

Intended location on ASUS laptop:

    C:\\Users\\ASUS\\Downloads\\kitchenware_yolo_dataset\\train_kitchenware_terminal.py

PowerShell:

    cd C:\\Users\\ASUS\\Downloads\\kitchenware_yolo_dataset
    python train_kitchenware_terminal.py
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import uuid
from pathlib import Path

from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = SCRIPT_DIR


def install_atomic_checkpoint_writer() -> None:
    if getattr(Path, "_hydroflow_atomic_checkpoint_writer", False):
        return
    original = Path.write_bytes

    def write_bytes(path: Path, data: bytes) -> int:
        if path.name not in {"last.pt", "best.pt"}:
            return original(path, data)
        tmp = path.with_name(f".{path.stem}-{uuid.uuid4().hex}.tmp")
        try:
            n = original(tmp, data)
            os.replace(tmp, path)
            return n
        finally:
            tmp.unlink(missing_ok=True)

    Path.write_bytes = write_bytes  # type: ignore[method-assign]
    Path._hydroflow_atomic_checkpoint_writer = True  # type: ignore[attr-defined]


def resolve_dataset_dir(path: Path) -> Path:
    path = path.expanduser().resolve()
    if (path / "data.yaml").is_file():
        return path
    nested = path / "kitchenware"
    if (nested / "data.yaml").is_file():
        return nested
    matches = sorted(path.rglob("data.yaml"))
    if len(matches) == 1:
        return matches[0].parent
    for yaml in matches:
        root = yaml.parent
        if (root / "train" / "images").is_dir():
            return root
    if matches:
        return matches[0].parent
    raise SystemExit(
        f"No data.yaml under {path}\n"
        "Unzip kitchenware_yolo_dataset so kitchenware/data.yaml exists."
    )


def prepare_data_yaml(dataset_dir: Path) -> Path:
    yaml_path = dataset_dir / "data.yaml"
    root_posix = dataset_dir.as_posix()
    yaml_path.write_text(
        f"path: {root_posix}\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        "nc: 8\n"
        "names: [plate, pot, soap, water_dipper, mug, bowl, knife, spoon]\n",
        encoding="utf-8",
    )
    return yaml_path


def resolve_weights(path: Path) -> Path:
    if path.is_file():
        return path
    for candidate in (SCRIPT_DIR / path.name, SCRIPT_DIR / path):
        if candidate.is_file():
            return candidate
    return path


def export_training_history(results_csv: Path, destination: Path) -> int:
    if not results_csv.is_file():
        raise SystemExit(f"Missing training log: {results_csv}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(results_csv, destination)
    with destination.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def print_history_preview(csv_path: Path, *, tail: int = 5) -> None:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return
    keys = ["epoch", "train/box_loss", "metrics/mAP50(B)", "metrics/mAP50-95(B)"]
    cols = [k for k in keys if k in rows[0]]
    print("--- training history (last epochs) ---")
    print(",".join(cols))
    for row in rows[-tail:]:
        print(",".join(str(row.get(c, "")) for c in cols))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train kitchenware YOLOv8m + export training_history.csv")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run-name", default="run_kitchenware")
    parser.add_argument("--weights", type=Path, default=Path("yolov8m.pt"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--device", default="0")
    parser.add_argument("--history-csv", type=Path, default=None)
    args = parser.parse_args()

    dataset_dir = resolve_dataset_dir(args.dataset_dir)
    data_yaml = prepare_data_yaml(dataset_dir)
    weights = resolve_weights(args.weights)
    if not weights.is_file():
        raise SystemExit(
            f"Weights not found: {args.weights}\nPut yolov8m.pt in {SCRIPT_DIR}"
        )
    device: str | int = int(args.device) if str(args.device).isdigit() else args.device
    history_dest = (args.history_csv or dataset_dir / "training_history.csv").resolve()

    install_atomic_checkpoint_writer()
    print(f"script dir: {SCRIPT_DIR}")
    print(f"dataset: {dataset_dir}")
    print(f"weights: {weights}")
    print(f"history csv: {history_dest}")

    YOLO(str(weights)).train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        device=device,
        amp=isinstance(device, int) or str(device).startswith("cuda") or str(device).isdigit(),
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        cos_lr=True,
        warmup_epochs=3,
        close_mosaic=10,
        seed=42,
        workers=0,
        val=True,
        save=True,
        plots=True,
        project=str(dataset_dir),
        name=args.run_name,
        exist_ok=True,
    )

    run_dir = dataset_dir / args.run_name
    best = run_dir / "weights" / "best.pt"
    history_src = run_dir / "results.csv"
    if not best.is_file():
        raise SystemExit(f"Missing weights: {best}")

    epochs = export_training_history(history_src, history_dest)
    shutil.copy2(best, dataset_dir / "best.pt")
    print(f"best.pt copy: {dataset_dir / 'best.pt'}")
    print(f"training_history.csv: {history_dest} ({epochs} epochs)")
    print_history_preview(history_dest)


if __name__ == "__main__":
    main()

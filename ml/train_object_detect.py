"""Train one YOLO detector per inventory class and copy the best weights.

The page loads ml/models/object_detect/<class>/best.pt. Datasets are the YOLO
splits already built under data/processed/object_detect.

Foods / kitchenware / utilities / clothing datasets:

    python ml/detection/build_foods_yolo_dataset.py --clean
    python ml/detection/build_kitchenware_yolo_dataset.py --clean
    python ml/detection/build_utilities_yolo_dataset.py --clean
    python ml/detection/build_clothing_yolo_dataset.py --clean
    python ml/train_object_detect.py --classes utilities --weights yolov8m.pt --epochs 100 --imgsz 640 --device 0 --batch 4 --patience 20
"""

from __future__ import annotations

import argparse
import os
import shutil
import uuid
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "object_detect"
# Keep paths short on Windows. Ultralytics writes a checkpoint every epoch.
RUNS = ROOT / "ml" / "runs" / "yolo"
SERVED = ROOT / "ml" / "models" / "object_detect"
CLASSES = ("clothing", "foods", "kitchenware", "utilities")


def install_atomic_checkpoint_writer() -> None:
    """Avoid intermittent Windows failures while overwriting last.pt/best.pt.

    Ultralytics writes those two files after every epoch. Writing a temporary
    sibling and atomically replacing the target avoids a direct overwrite that
    can fail on some Windows file-system or antivirus configurations.
    """
    if getattr(Path, "_hydroflow_atomic_checkpoint_writer", False):
        return
    original_write_bytes = Path.write_bytes

    def write_bytes_atomically(path: Path, data: bytes) -> int:
        if path.name not in {"last.pt", "best.pt"}:
            return original_write_bytes(path, data)
        temporary = path.with_name(f".{path.stem}-{uuid.uuid4().hex}.tmp")
        try:
            written = original_write_bytes(temporary, data)
            os.replace(temporary, path)
            return written
        finally:
            temporary.unlink(missing_ok=True)

    Path.write_bytes = write_bytes_atomically  # type: ignore[method-assign]
    Path._hydroflow_atomic_checkpoint_writer = True  # type: ignore[attr-defined]


def assert_checkpoint_directory_writable(run_root: Path, run_name: str) -> None:
    """Fail before training if Windows cannot create a YOLO checkpoint."""
    weights = run_root / run_name / "weights"
    weights.mkdir(parents=True, exist_ok=True)
    probe = weights / ".checkpoint-write-probe"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        raise SystemExit(f"Checkpoint directory is not writable: {weights}: {exc}") from exc


def train_one(
    name: str,
    *,
    run_name: str,
    run_root: Path,
    promote: bool,
    weights: Path,
    epochs: int,
    imgsz: int,
    patience: int,
    device: str | int,
    batch: int,
) -> Path:
    data = DATA / name / "data.yaml"
    if not data.is_file():
        raise SystemExit(f"Missing dataset: {data}")
    assert_checkpoint_directory_writable(run_root, run_name)
    install_atomic_checkpoint_writer()
    model = YOLO(weights)
    model.train(
        data=str(data),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        patience=patience,
        device=device,
        amp=isinstance(device, int) or str(device).startswith("cuda") or str(device).isdigit(),
        deterministic=False,
        project=str(run_root),
        name=run_name,
        exist_ok=True,
        pretrained=True,
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        cos_lr=True,
        warmup_epochs=3,
        close_mosaic=10,
        seed=42,
        workers=0,
        cache=False,
        plots=False,
        val=True,
        save=True,
    )
    run_dir = run_root / run_name
    best = run_dir / "weights" / "best.pt"
    if not best.is_file():
        raise SystemExit(f"Training finished without weights: {best}")
    history_src = run_dir / "results.csv"
    if not history_src.is_file():
        raise SystemExit(f"Training finished without metrics log: {history_src}")
    destination = SERVED / name
    destination.mkdir(parents=True, exist_ok=True)
    history_dest = destination / "training_history.csv"
    shutil.copy2(history_src, history_dest)
    print(f"training history: {history_dest} ({history_src.stat().st_size} bytes)")
    if not promote:
        return best
    shutil.copy2(best, destination / "best.pt")
    return destination / "best.pt"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train HydroFlow inventory YOLO candidates.")
    parser.add_argument("--run-prefix", default="run_", help="Prefix for an isolated candidate run.")
    parser.add_argument("--run-root", type=Path, default=RUNS, help="Directory for YOLO run output.")
    parser.add_argument(
        "--classes",
        nargs="+",
        choices=CLASSES,
        default=CLASSES,
        help="One or more inventory model groups to train.",
    )
    parser.add_argument("--promote", action="store_true", help="Copy candidates into the served model paths.")
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "yolov8n.pt",
        help="Starter checkpoint (e.g. yolov8s.pt for foods).",
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument(
        "--device",
        default="cpu",
        help='Training device: cpu, 0, cuda, etc.',
    )
    parser.add_argument("--batch", type=int, default=8)
    args = parser.parse_args()
    device: str | int = int(args.device) if str(args.device).isdigit() else args.device
    weights = args.weights if args.weights.is_file() else Path(str(args.weights))
    for name in args.classes:
        run_name = f"{args.run_prefix}{name}" if args.run_prefix else name
        saved = train_one(
            name,
            run_name=run_name,
            run_root=args.run_root,
            promote=args.promote,
            weights=weights,
            epochs=args.epochs,
            imgsz=args.imgsz,
            patience=args.patience,
            device=device,
            batch=args.batch,
        )
        print(f"trained {name}: {saved}")


if __name__ == "__main__":
    main()

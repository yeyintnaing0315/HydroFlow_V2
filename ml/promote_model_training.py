"""Copy trained weights from model_training/ into ml/models/object_detect/.

Usage (from repo root):

    python ml/promote_model_training.py foods kitchenware
    python ml/promote_model_training.py clothing utilities
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVED = ROOT / "ml" / "models" / "object_detect"

# Folder name under ml/models/object_detect/ -> best.pt under model_training/
_SOURCES: dict[str, tuple[Path, Path]] = {
    "foods": (
        ROOT / "model_training" / "food" / "runs" / "detect" / "runs" / "foods_yolov8m" / "weights" / "best.pt",
        ROOT / "model_training" / "food" / "runs" / "detect" / "runs" / "foods_yolov8m" / "results.csv",
    ),
    "kitchenware": (
        ROOT / "model_training" / "kitchenware" / "runs" / "detect" / "kitchenware_yolov8m" / "weights" / "best.pt",
        ROOT / "model_training" / "kitchenware" / "runs" / "detect" / "kitchenware_yolov8m" / "results.csv",
    ),
    "clothing": (
        ROOT / "model_training" / "clothing" / "runs" / "detect" / "clothing_yolov8m" / "weights" / "best.pt",
        ROOT / "model_training" / "clothing" / "runs" / "detect" / "clothing_yolov8m" / "results.csv",
    ),
    "utilities": (
        ROOT / "model_training" / "Utility" / "runs" / "detect" / "utilities_yolov8m" / "weights" / "best.pt",
        ROOT / "model_training" / "Utility" / "runs" / "detect" / "utilities_yolov8m" / "results.csv",
    ),
}


def promote(name: str) -> None:
    if name not in _SOURCES:
        raise SystemExit(f"Unknown class {name!r}. Choose from: {', '.join(sorted(_SOURCES))}")
    weights_src, history_src = _SOURCES[name]
    if not weights_src.is_file():
        raise SystemExit(f"Missing weights: {weights_src}")
    dest_dir = SERVED / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(weights_src, dest_dir / "best.pt")
    if history_src.is_file():
        shutil.copy2(history_src, dest_dir / "training_history.csv")
    print(f"promoted {name}: {dest_dir / 'best.pt'} ({weights_src.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote model_training YOLOv8m weights into ml/models/object_detect/")
    parser.add_argument(
        "classes",
        nargs="+",
        choices=sorted(_SOURCES),
        help="Served folder names under ml/models/object_detect/.",
    )
    args = parser.parse_args()
    for name in args.classes:
        promote(name)


if __name__ == "__main__":
    main()

"""
Train YOLOv8m on the kitchenware YOLO dataset and collect training history.

Dataset layout (relative to this script):
  kitchenware/
    data.yaml
    train/images + train/labels   (6400)
    valid/images + valid/labels   (800)
    test/images  + test/labels    (800)

Classes (8): plate, pot, soap, dipper, mug, bowl, knife, spoon

Outputs under runs/detect/<run_name>/:
  - weights/best.pt, weights/last.pt
  - results.csv              (Ultralytics per-epoch metrics)
  - training_history.json    (structured history + best/final)
  - training_history.csv     (cleaned epoch table)
  - history_curves.png       (loss + mAP plots, if matplotlib available)
  - test_metrics.json        (optional eval on test split)

Usage (from this folder, with the local .venv):
  .\\.venv\\Scripts\\python.exe train_yolov8m.py
  .\\.venv\\Scripts\\python.exe train_yolov8m.py --epochs 50 --batch 4 --device cpu
  .\\.venv\\Scripts\\python.exe train_yolov8m.py --device 0 --batch 16   # if CUDA GPU available
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parent
DATA_YAML = ROOT / "kitchenware" / "data.yaml"
DEFAULT_PROJECT = ROOT / "runs" / "detect"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train YOLOv8m on kitchenware dataset")
    p.add_argument("--data", type=Path, default=DATA_YAML, help="Path to data.yaml")
    p.add_argument("--model", type=str, default="yolov8m.pt", help="Base model weights")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=8, help="Use -1 for AutoBatch")
    p.add_argument("--device", type=str, default="cpu", help="cpu, 0, 0,1, etc.")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    p.add_argument("--name", type=str, default="kitchenware_yolov8m")
    p.add_argument("--patience", type=int, default=30, help="Early-stopping patience")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--resume", action="store_true", help="Resume last interrupted run")
    p.add_argument("--exist-ok", action="store_true", help="Overwrite run folder if it exists")
    p.add_argument("--skip-test", action="store_true", help="Skip post-train test evaluation")
    return p.parse_args()


def _serialize(obj):
    """JSON-safe conversion for Ultralytics metric values."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return str(obj)


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_results_csv(results_csv: Path) -> list[dict]:
    rows: list[dict] = []
    with open(results_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
            # Coerce numeric fields when possible
            coerced = {}
            for k, v in row.items():
                num = _to_float(v)
                coerced[k] = num if num is not None else v
            rows.append(coerced)
    return rows


def collect_history(results, save_dir: Path) -> dict:
    """Build structured training history from Ultralytics results.csv."""
    save_dir = Path(save_dir)
    history: dict = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "save_dir": str(save_dir),
        "epochs": [],
        "best": {},
        "final": {},
        "source_csv": None,
    }

    results_csv = save_dir / "results.csv"
    if results_csv.exists():
        history["source_csv"] = str(results_csv)
        rows = read_results_csv(results_csv)
        history["epochs"] = _serialize(rows)

        if rows:
            metric_keys = [k for k in rows[0].keys() if k != "epoch"]
            rank_col = next(
                (k for k in rows[0].keys() if "mAP50-95" in k or "map50-95" in k.lower()),
                None,
            )
            if rank_col is None:
                rank_col = next((k for k in rows[0].keys() if "mAP50" in k), None)

            if rank_col is not None:
                scored = [(i, _to_float(r.get(rank_col))) for i, r in enumerate(rows)]
                scored = [(i, v) for i, v in scored if v is not None]
                if scored:
                    best_i, _ = max(scored, key=lambda t: t[1])
                    best_row = rows[best_i]
                    history["best"] = {
                        "epoch": int(best_row.get("epoch", best_i + 1)),
                        "rank_metric": rank_col,
                        "metrics": _serialize({k: best_row.get(k) for k in metric_keys}),
                    }

            last = rows[-1]
            history["final"] = {
                "epoch": int(last.get("epoch", len(rows))),
                "metrics": _serialize({k: last.get(k) for k in metric_keys}),
            }

    trainer = getattr(results, "trainer", None) or getattr(results, "_trainer", None)
    if trainer is not None:
        history["trainer"] = {
            "best_fitness": _serialize(getattr(trainer, "best_fitness", None)),
            "best_epoch": _serialize(getattr(trainer, "best_epoch", None)),
            "epoch": _serialize(getattr(trainer, "epoch", None)),
        }

    json_path = save_dir / "training_history.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print(f"[history] wrote {json_path}")

    csv_path = save_dir / "training_history.csv"
    if history["epochs"]:
        fieldnames = list(history["epochs"][0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(history["epochs"])
        print(f"[history] wrote {csv_path} ({len(history['epochs'])} epochs)")

    if results_csv.exists():
        plot_history_curves(results_csv, save_dir / "history_curves.png")

    return history


def plot_history_curves(results_csv: Path, out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[history] matplotlib not installed; skipping history_curves.png")
        return

    rows = read_results_csv(results_csv)
    if not rows:
        return

    epochs = [r.get("epoch", i + 1) for i, r in enumerate(rows)]
    keys = list(rows[0].keys())
    loss_cols = [k for k in keys if "loss" in k.lower()][:6]
    map_cols = [k for k in keys if k in ("metrics/mAP50(B)", "metrics/mAP50-95(B)")]
    if not map_cols:
        map_cols = [k for k in keys if "map" in k.lower() or "mAP" in k][:4]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    ax = axes[0]
    for col in loss_cols:
        ax.plot(epochs, [r.get(col) for r in rows], label=col)
    ax.set_title("Loss")
    ax.set_xlabel("Epoch")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    for col in map_cols:
        ax.plot(epochs, [r.get(col) for r in rows], label=col)
    ax.set_title("mAP")
    ax.set_xlabel("Epoch")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[history] wrote {out_path}")


def main() -> int:
    args = parse_args()

    if not args.data.exists():
        print(f"ERROR: data.yaml not found at {args.data}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("YOLOv8m kitchenware training")
    print("=" * 60)
    print(f"data     : {args.data}")
    print(f"model    : {args.model}")
    print(f"epochs   : {args.epochs}")
    print(f"imgsz    : {args.imgsz}")
    print(f"batch    : {args.batch}")
    print(f"device   : {args.device}")
    print(f"project  : {args.project}")
    print(f"name     : {args.name}")
    print("=" * 60)

    model = YOLO(args.model)

    results = model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project=str(args.project),
        name=args.name,
        patience=args.patience,
        seed=args.seed,
        resume=args.resume,
        exist_ok=args.exist_ok,
        plots=True,
        save=True,
        verbose=True,
    )

    save_dir = Path(getattr(results, "save_dir", args.project / args.name))
    if not save_dir.exists():
        candidates = sorted(args.project.glob(f"{args.name}*"), key=lambda p: p.stat().st_mtime)
        if candidates:
            save_dir = candidates[-1]

    history = collect_history(results, save_dir)

    if not args.skip_test:
        try:
            print("\nRunning validation on best weights (test split)...")
            best = save_dir / "weights" / "best.pt"
            if best.exists():
                best_model = YOLO(str(best))
                metrics = best_model.val(data=str(args.data), split="test", device=args.device)
                test_summary = {
                    "map50": _serialize(getattr(metrics.box, "map50", None)),
                    "map50_95": _serialize(getattr(metrics.box, "map", None)),
                    "precision": _serialize(getattr(metrics.box, "mp", None)),
                    "recall": _serialize(getattr(metrics.box, "mr", None)),
                }
                test_path = save_dir / "test_metrics.json"
                with open(test_path, "w", encoding="utf-8") as f:
                    json.dump(test_summary, f, indent=2)
                print(f"[history] wrote {test_path}")
                print(
                    f"Test mAP50={test_summary['map50']}  "
                    f"mAP50-95={test_summary['map50_95']}"
                )
        except Exception as exc:
            print(f"[warn] test evaluation skipped: {exc}")

    print("\nDone.")
    print(f"Run directory : {save_dir}")
    print(f"Best weights  : {save_dir / 'weights' / 'best.pt'}")
    if history.get("best"):
        print(f"Best epoch    : {history['best'].get('epoch')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

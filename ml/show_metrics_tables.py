"""Print evaluation JSON as terminal tables (for slides / screenshots)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def _table(title: str, rows: list[dict]) -> None:
    print(f"\n=== {title} ===")
    print(pd.DataFrame(rows).to_string(index=False))


def flood_prediction() -> None:
    path = ARTIFACTS / "evaluation_metrics.json"
    if not path.is_file():
        print(f"Missing {path} — run: ml/run.py train && ml/run.py evaluate")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for split in ("validation", "test"):
        block = data[split]
        rows.append(
            {
                "split": split,
                "precision": round(block["precision"], 4),
                "recall": round(block["recall"], 4),
                "f1": round(block["f1"], 4),
                "pr_auc": round(block["pr_auc_average_precision"], 4),
                "roc_auc": round(block["roc_auc"], 4),
                "flood_rows": block["flood_rows"],
                "total_rows": block["rows"],
            }
        )
    _table("Flood prediction", rows)

    cm = data["test"]["confusion_matrix"]
    _table(
        "Test confusion matrix",
        [
            {"": "TN", "count": cm["tn"]},
            {"": "FP", "count": cm["fp"]},
            {"": "FN", "count": cm["fn"]},
            {"": "TP", "count": cm["tp"]},
        ],
    )

    comp = data.get("baseline_comparison", {})
    if comp:
        baseline_rows = []
        for label, key in (
            ("Current model (test)", "current_model_test"),
            ("Naive always negative", "naive_always_negative"),
            ("Naive always positive", "naive_always_positive"),
        ):
            b = comp[key]
            baseline_rows.append(
                {
                    "model": label,
                    "precision": round(b["precision"], 4),
                    "recall": round(b["recall"], 4),
                    "f1": round(b["f1"], 4),
                }
            )
        pub = comp.get("published_hydroflow_random_forest", {})
        if pub:
            baseline_rows.append(
                {
                    "model": "Published RandomForest",
                    "precision": pub.get("flood_precision"),
                    "recall": pub.get("flood_recall"),
                    "f1": pub.get("flood_f1"),
                }
            )
        _table("Baseline comparison", baseline_rows)


def flood_help() -> None:
    path = ARTIFACTS / "help_evaluation_metrics.json"
    if not path.is_file():
        print(f"Missing {path} — run: ml/run.py train-help && ml/run.py evaluate-help")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for split in ("validation", "test"):
        block = data[split]
        rows.append(
            {
                "split": split,
                "precision": round(block["precision"], 4),
                "recall": round(block["recall"], 4),
                "f1": round(block["f1"], 4),
                "people_mae": round(block["expected_affected_people_mae"], 1),
                "households_mae": round(block["expected_households_mae"], 1),
                "help_rows": block["help_rows"],
            }
        )
    _table("Flood help (allocation input)", rows)


def main() -> None:
    flood_prediction()
    flood_help()
    print()


if __name__ == "__main__":
    main()

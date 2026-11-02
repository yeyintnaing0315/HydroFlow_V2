from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .config import FEATURE_DATA, RAW_DATA
from .eda import create_eda_summary
from .evaluation import evaluate
from .features import build_feature_data
from .allocation_model import train_allocation
from .help_model import evaluate_help, predict_help_rows, train_help
from .topredict_eda import create_topredict_summary
from .inference import predict_feature_rows
from .ingest import ingest, load_raw
from .model import train
from .validation import validate_daily_data


def _load_features() -> pd.DataFrame:
    if not FEATURE_DATA.exists():
        raise FileNotFoundError("Run `python ml/run.py process` first")
    return pd.read_csv(FEATURE_DATA, parse_dates=["date"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HydroFlow V2 ML pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "validate",
        "process",
        "eda",
        "train",
        "evaluate",
        "train-help",
        "evaluate-help",
        "analyze-topredict",
        "train-allocation",
        "run-all",
    ):
        subparsers.add_parser(command)
    predict_parser = subparsers.add_parser("predict")
    predict_parser.add_argument("input", type=Path, help="CSV containing engineered model features")
    predict_parser.add_argument("--output", type=Path)
    predict_help_parser = subparsers.add_parser("predict-help")
    predict_help_parser.add_argument("input", type=Path, help="CSV containing engineered model features")
    predict_help_parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.command == "validate":
        result = validate_daily_data(load_raw(RAW_DATA)).as_dict()
    elif args.command == "process":
        data, report = ingest()
        features = build_feature_data(data)
        result = {**report.as_dict(), "feature_rows": len(features)}
    elif args.command == "eda":
        data, report = ingest()
        result = {"validation": report.as_dict(), **create_eda_summary(data)}
    elif args.command == "train":
        _, result, _ = train(_load_features())
    elif args.command == "evaluate":
        result = evaluate(_load_features())
    elif args.command == "train-help":
        _, result, _ = train_help(_load_features())
    elif args.command == "evaluate-help":
        result = evaluate_help(_load_features())
    elif args.command == "analyze-topredict":
        result = create_topredict_summary()
    elif args.command == "train-allocation":
        _, metadata = train_allocation()
        result = {"version": metadata["version"], "training_rows": metadata["training_rows"]}
    elif args.command in {"predict", "predict-help"}:
        data = pd.read_csv(args.input)
        output = predict_feature_rows(data) if args.command == "predict" else predict_help_rows(data)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            output.to_csv(args.output, index=False)
            result = {"rows": len(output), "output": str(args.output)}
        else:
            print(output.to_csv(index=False), end="")
            return 0
    else:
        data, report = ingest()
        features = build_feature_data(data)
        eda = create_eda_summary(data)
        _, metadata, _ = train(features)
        metrics = evaluate(features)
        _, help_metadata, _ = train_help(features)
        help_metrics = evaluate_help(features)
        result = {
            "validation": report.as_dict(),
            "eda": {"flood_rate": eda["flood_rate"]},
            "training": metadata["split"],
            "test_metrics": metrics["test"],
            "help_model": {
                "version": help_metadata["version"],
                "validation_f1": help_metadata["validation_f1_at_selected_threshold"],
                "test_f1": help_metrics["test"]["f1"],
                "test_expected_people_mae": help_metrics["test"]["expected_affected_people_mae"],
            },
        }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

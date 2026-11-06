"""Train a chronological-split logistic-regression fraud baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pyarrow.parquet as pq
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


NUMERIC = [
    "amount",
    "device_first_seen_days",
    "transaction_count_1h",
    "amount_sum_1h",
    "distinct_merchant_count_1h",
    "new_device_count_1h",
]
CATEGORICAL = ["currency", "channel", "country_code"]
FEATURES = NUMERIC + CATEGORICAL
SPLITS = ["TRAIN", "VALIDATION", "TEST"]


def load_split(root: Path, split: str) -> tuple[np.ndarray, np.ndarray, set[str]]:
    files = sorted((root / f"dataset_split={split}").glob("*"))
    files = [path for path in files if path.is_file()]
    if not files:
        raise FileNotFoundError(f"No Parquet files found for split {split} under {root}")

    records: list[dict[str, Any]] = []
    for path in files:
        records.extend(pq.read_table(path).to_pylist())

    payment_ids = {row["payment_id"] for row in records}
    if len(payment_ids) != len(records):
        raise ValueError(f"Duplicate payment_id found in {split} split")

    matrix = np.asarray(
        [[row[name] for name in FEATURES] for row in records],
        dtype=object,
    )
    labels = np.asarray([int(row["label_fraud"]) for row in records], dtype=np.int32)
    return matrix, labels, payment_ids


def score_split(y_true: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict[str, Any]:
    predictions = (probabilities >= threshold).astype(np.int32)
    return {
        "rows": int(len(y_true)),
        "fraud_count": int(y_true.sum()),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "average_precision": float(average_precision_score(y_true, probabilities)),
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, predictions).tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        default="work/ml/training-export",
        help="Root directory containing dataset_split=... Parquet folders.",
    )
    parser.add_argument("--output-dir", default="work/ml/baseline")
    args = parser.parse_args()

    root = Path(args.input_dir)
    loaded = {split: load_split(root, split) for split in SPLITS}

    id_sets = {split: loaded[split][2] for split in SPLITS}
    for left, right in (("TRAIN", "VALIDATION"), ("TRAIN", "TEST"), ("VALIDATION", "TEST")):
        overlap = id_sets[left] & id_sets[right]
        if overlap:
            raise ValueError(f"{len(overlap)} payment IDs overlap between {left} and {right}")

    x_train, y_train, _ = loaded["TRAIN"]
    x_val, y_val, _ = loaded["VALIDATION"]
    x_test, y_test, _ = loaded["TEST"]

    preprocess = ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), list(range(len(NUMERIC)))),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                list(range(len(NUMERIC), len(FEATURES))),
            ),
        ]
    )
    model = Pipeline([
        ("preprocess", preprocess),
        ("classifier", LogisticRegression(
            class_weight="balanced",
            max_iter=2000,
            random_state=7,
        )),
    ])
    model.fit(x_train, y_train)

    validation_probabilities = model.predict_proba(x_val)[:, 1]
    precision, recall, thresholds = precision_recall_curve(y_val, validation_probabilities)
    if len(thresholds):
        f1_values = (
            2 * precision[:-1] * recall[:-1]
            / np.maximum(precision[:-1] + recall[:-1], 1e-12)
        )
        threshold = float(thresholds[int(np.nanargmax(f1_values))])
    else:
        threshold = 0.5

    test_probabilities = model.predict_proba(x_test)[:, 1]
    results = {
        "model": "logistic_regression_baseline",
        "label": "label_fraud",
        "features": FEATURES,
        "threshold_selected_on": "VALIDATION",
        "validation": score_split(y_val, validation_probabilities, threshold),
        "test": score_split(y_test, test_probabilities, threshold),
        "split_rows": {split: int(len(loaded[split][1])) for split in SPLITS},
    }

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "threshold": threshold, "features": FEATURES},
        output / "logistic_regression_baseline.joblib",
    )
    (output / "metrics.json").write_text(json.dumps(results, indent=2) + "\n")

    print(json.dumps(results, indent=2))
    print(f"Saved model and metrics under {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

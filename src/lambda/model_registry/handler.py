"""Gate SageMaker Model Registry versions on held-out fraud ROC-AUC."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
S3 = boto3.client("s3")
SAGEMAKER = boto3.client("sagemaker")
MODEL_PACKAGE_GROUP = os.environ["MODEL_PACKAGE_GROUP"]
INFERENCE_IMAGE = os.environ["INFERENCE_IMAGE"]
MODEL_PREFIX = os.environ.get("MODEL_PREFIX", "ml/models/")

INFERENCE_CODE = '''from __future__ import annotations
import csv
import io
import json
from pathlib import Path
import joblib
import numpy as np

def model_fn(model_dir):
    return joblib.load(Path(model_dir) / "logistic_regression_baseline.joblib")

def input_fn(request_body, content_type):
    if content_type == "application/json":
        payload = json.loads(request_body)
        rows = payload.get("instances", payload) if isinstance(payload, dict) else payload
        return np.asarray(rows, dtype=object)
    if content_type == "text/csv":
        return np.asarray(list(csv.reader(io.StringIO(request_body))), dtype=object)
    raise ValueError("Supported content types are application/json and text/csv")

def predict_fn(data, artifact):
    model = artifact["model"]
    probabilities = model.predict_proba(data)[:, 1]
    threshold = float(artifact["threshold"])
    return {"fraud_probability": probabilities.tolist(),
            "fraud_prediction": (probabilities >= threshold).astype(int).tolist(),
            "threshold": threshold}

def output_fn(prediction, accept):
    if accept not in ("application/json", "*/*"):
        raise ValueError("Only application/json output is supported")
    return json.dumps(prediction), "application/json"
'''


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"Expected an S3 object URI, got {uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


def load_metrics(uri: str) -> tuple[dict, float]:
    bucket, key = parse_s3_uri(uri)
    response = S3.get_object(Bucket=bucket, Key=key)
    metrics = json.loads(response["Body"].read())
    score = float(metrics["test"]["roc_auc"])
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"Invalid held-out test ROC-AUC {score}")
    return metrics, score


def registered_packages() -> list[dict]:
    packages = []
    paginator = SAGEMAKER.get_paginator("list_model_packages")
    for page in paginator.paginate(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP,
        SortBy="CreationTime",
        SortOrder="Descending",
    ):
        packages.extend(page.get("ModelPackageSummaryList", []))
    return packages


def lambda_handler(event: dict, context: object) -> dict:
    model_bucket, model_key = parse_s3_uri(event["model_uri"])
    metrics, candidate_score = load_metrics(event["metrics_uri"])
    export_id = str(event["export_id"])
    existing = registered_packages()

    for package in existing:
        metadata = package.get("CustomerMetadataProperties", {})
        if metadata.get("export_id") == export_id and package.get("ModelPackageStatus") == "Completed":
            return {
                "status": "ALREADY_REGISTERED",
                "model_package_arn": package["ModelPackageArn"],
                "test_roc_auc": candidate_score,
            }

    best_score = max(
        (float(p["CustomerMetadataProperties"]["test_roc_auc"])
         for p in existing
         if p.get("ModelPackageStatus") == "Completed"
         and p.get("CustomerMetadataProperties", {}).get("test_roc_auc") is not None),
        default=None,
    )
    if best_score is not None and candidate_score <= best_score:
        LOGGER.info("Candidate ROC-AUC %s did not exceed registered best %s", candidate_score, best_score)
        return {
            "status": "NOT_REGISTERED",
            "model_package_arn": "",
            "test_roc_auc": candidate_score,
            "best_registered_test_roc_auc": best_score,
        }

    with tempfile.TemporaryDirectory(prefix="sentinelpay-model-package-") as temp_dir:
        root = Path(temp_dir)
        S3.download_file(model_bucket, model_key, str(root / "logistic_regression_baseline.joblib"))
        code_dir = root / "code"
        code_dir.mkdir()
        (code_dir / "inference.py").write_text(INFERENCE_CODE)
        archive_path = root / "model.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(root / "logistic_regression_baseline.joblib", arcname="logistic_regression_baseline.joblib")
            archive.add(code_dir, arcname="code")

        artifact_key = f"{MODEL_PREFIX}registry/candidates/export_id={export_id}/model.tar.gz"
        S3.upload_file(
            str(archive_path), model_bucket, artifact_key,
            ExtraArgs={"ContentType": "application/gzip", "ServerSideEncryption": "aws:kms"},
        )

    response = SAGEMAKER.create_model_package(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP,
        ModelPackageDescription=f"Glue-trained fraud model; export {export_id}; test ROC-AUC {candidate_score:.8f}",
        ModelApprovalStatus="PendingManualApproval",
        InferenceSpecification={
            "Containers": [{
                "Image": INFERENCE_IMAGE,
                "ModelDataUrl": f"s3://{model_bucket}/{artifact_key}",
                "Environment": {"SAGEMAKER_PROGRAM": "inference.py"},
            }],
            "SupportedContentTypes": ["application/json", "text/csv"],
            "SupportedResponseMIMETypes": ["application/json"],
        },
        CustomerMetadataProperties={
            "export_id": export_id,
            "test_roc_auc": f"{candidate_score:.10f}",
            "metric_name": "test_roc_auc",
            "training_source": "glue_export_lambda_trainer",
        },
    )
    return {
        "status": "REGISTERED_PENDING_APPROVAL",
        "model_package_arn": response["ModelPackageArn"],
        "test_roc_auc": candidate_score,
        "previous_best_test_roc_auc": best_score if best_score is not None else "none",
        "test_rows": int(metrics["test"]["rows"]),
    }

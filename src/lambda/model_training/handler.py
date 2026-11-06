"""Train a versioned fraud model after Glue publishes a successful export manifest."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote_plus, urlparse
from typing import Any

import boto3
import pyarrow.parquet as pq
from botocore.exceptions import ClientError

from train_baseline import SPLITS, load_split, train_loaded_splits


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
S3 = boto3.client("s3")
SAGEMAKER = boto3.client("sagemaker")
MANIFEST_PREFIX = os.environ.get("MANIFEST_PREFIX", "ops/glue_batch_runs/")
EXPORT_PREFIX = os.environ.get("EXPORT_PREFIX", "ml/training_exports/glue/")
MODEL_PREFIX = os.environ.get("MODEL_PREFIX", "ml/models/")
MINIMUM_ROWS = {
    "TRAIN": int(os.environ.get("MIN_TRAIN_ROWS", "500")),
    "VALIDATION": int(os.environ.get("MIN_VALIDATION_ROWS", "100")),
    "TEST": int(os.environ.get("MIN_TEST_ROWS", "100")),
}
MINIMUM_FRAUD_ROWS = int(os.environ.get("MIN_FRAUD_ROWS_PER_SPLIT", "10"))
MINIMUM_LABEL_DELAY_DAYS = int(os.environ.get("MIN_LABEL_DELAY_DAYS", "30"))
MAX_EXPORT_BYTES = int(os.environ.get("MAX_EXPORT_BYTES", str(2 * 1024**3)))
TRAINING_LOCK_SECONDS = 20 * 60
MODEL_REGISTRY_PIPELINE_NAME = os.environ.get("MODEL_REGISTRY_PIPELINE_NAME", "")


def start_registry_pipeline(bucket: str, run_id: str, model_key: str, metrics_key: str) -> str | None:
    """Hand the completed Glue-trained model to the separate SageMaker registry flow."""
    if not MODEL_REGISTRY_PIPELINE_NAME:
        LOGGER.info("Model registry pipeline is not configured; leaving trained artifacts in S3")
        return None
    response = SAGEMAKER.start_pipeline_execution(
        PipelineName=MODEL_REGISTRY_PIPELINE_NAME,
        PipelineParameters=[
            {"Name": "ModelUri", "Value": f"s3://{bucket}/{model_key}"},
            {"Name": "MetricsUri", "Value": f"s3://{bucket}/{metrics_key}"},
            {"Name": "ExportId", "Value": run_id},
        ],
    )
    return response["PipelineExecutionArn"]


def object_exists(bucket: str, key: str) -> bool:
    response = S3.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1)
    return any(item["Key"] == key for item in response.get("Contents", []))


def split_objects(bucket: str, export_prefix: str, split: str) -> list[dict[str, Any]]:
    prefix = f"{export_prefix}dataset_split={split}/"
    paginator = S3.get_paginator("list_objects_v2")
    objects = [
        item
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for item in page.get("Contents", [])
        if item["Key"].endswith(".parquet")
    ]
    return sorted(objects, key=lambda item: item["Key"])


def validate_manifest_export(
    manifest: dict[str, Any], bucket: str
) -> tuple[str, str, dict[str, int]] | None:
    if manifest.get("status") != "SUCCEEDED":
        LOGGER.info("Skipping unsuccessful Glue run %s", manifest.get("run_id"))
        return None
    if manifest.get("data_classification") != "SYNTHETIC":
        raise ValueError("Training Lambda accepts only SYNTHETIC exports")

    gold = manifest.get("gold") or {}
    export_uri = gold.get("training_export_uri")
    split_rows = gold.get("dataset_split_rows") or {}
    if not export_uri:
        LOGGER.info("Skipping Glue run with no Gold export: %s", manifest.get("run_id"))
        return None
    parsed = urlparse(export_uri)
    if parsed.scheme != "s3" or parsed.netloc != bucket:
        raise ValueError("Gold export must be in the same project bucket as its manifest")
    export_prefix = parsed.path.lstrip("/")
    if not export_prefix.startswith(EXPORT_PREFIX) or not export_prefix.endswith("/"):
        raise ValueError("Gold export URI is outside the configured training export prefix")

    counts = {split: int(split_rows.get(split, 0)) for split in SPLITS}
    for split, minimum in MINIMUM_ROWS.items():
        if counts[split] < minimum:
            LOGGER.info(
                "Skipping immature export %s: %s has %s rows; requires %s",
                manifest.get("run_id"), split, counts[split], minimum,
            )
            return None
    return export_prefix, str(manifest.get("run_id", "")), counts


def validate_label_maturity(parquet_path: Path) -> None:
    delays = pq.read_table(parquet_path, columns=["label_delay_days"])[
        "label_delay_days"
    ].to_pylist()
    if not delays:
        raise ValueError(f"Empty Parquet file: {parquet_path.name}")
    if any(delay is None or int(delay) < MINIMUM_LABEL_DELAY_DAYS for delay in delays):
        raise ValueError(
            f"{parquet_path.name} contains labels younger than "
            f"{MINIMUM_LABEL_DELAY_DAYS} days"
        )


def acquire_training_lock(bucket: str, run_id: str) -> tuple[str, str] | None:
    lock_key = f"{MODEL_PREFIX}locks/export_id={run_id}.json"
    for _ in range(2):
        now = int(datetime.now(timezone.utc).timestamp())
        lock_body = json.dumps({"run_id": run_id, "expires_at": now + TRAINING_LOCK_SECONDS})
        try:
            response = S3.put_object(
                Bucket=bucket,
                Key=lock_key,
                Body=lock_body.encode("utf-8"),
                ContentType="application/json",
                ServerSideEncryption="aws:kms",
                IfNoneMatch="*",
            )
            return lock_key, response["ETag"]
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in {"PreconditionFailed", "ConditionalRequestConflict", "412"}:
                raise

        try:
            response = S3.get_object(Bucket=bucket, Key=lock_key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404", "NotFound"}:
                continue
            raise
        with response["Body"] as body:
            existing_lock = json.loads(body.read())
        if int(existing_lock.get("expires_at", 0)) > int(datetime.now(timezone.utc).timestamp()):
            return None
        try:
            S3.delete_object(Bucket=bucket, Key=lock_key, IfMatch=response["ETag"])
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"PreconditionFailed", "ConditionalRequestConflict", "412"}:
                return None
            raise
    return None


def train_export(
    bucket: str,
    manifest_key: str,
    manifest: dict[str, Any],
    export_prefix: str,
    run_id: str,
    expected_rows: dict[str, int],
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Glue run ID contains unsupported characters")
    output_prefix = f"{MODEL_PREFIX}export_id={run_id}/"
    model_key = f"{output_prefix}logistic_regression_baseline.joblib"
    metrics_key = f"{output_prefix}metrics.json"
    if object_exists(bucket, metrics_key):
        LOGGER.info("Model already trained for export %s; skipping duplicate event", run_id)
        pipeline_arn = start_registry_pipeline(bucket, run_id, model_key, metrics_key)
        return {
            "status": "ALREADY_TRAINED",
            "export_id": run_id,
            "registry_pipeline_execution_arn": pipeline_arn,
        }

    lock = acquire_training_lock(bucket, run_id)
    if lock is None:
        LOGGER.info("Training is already in progress for export %s", run_id)
        return {"status": "ALREADY_TRAINING", "export_id": run_id}
    lock_key, lock_etag = lock

    try:
        result = _train_export_locked(
            bucket, manifest_key, manifest, export_prefix, run_id,
            expected_rows, model_key, metrics_key,
        )
        if result.get("status") in {"TRAINED", "ALREADY_TRAINED"}:
            result["registry_pipeline_execution_arn"] = start_registry_pipeline(
                bucket, run_id, model_key, metrics_key
            )
        return result
    finally:
        S3.delete_object(Bucket=bucket, Key=lock_key, IfMatch=lock_etag)


def _train_export_locked(
    bucket: str,
    manifest_key: str,
    manifest: dict[str, Any],
    export_prefix: str,
    run_id: str,
    expected_rows: dict[str, int],
    model_key: str,
    metrics_key: str,
) -> dict[str, Any]:
    if object_exists(bucket, metrics_key):
        LOGGER.info("Model already trained for export %s; skipping duplicate event", run_id)
        return {"status": "ALREADY_TRAINED", "export_id": run_id}

    files_by_split: dict[str, list[dict[str, Any]]] = {}
    total_bytes = 0
    for split in SPLITS:
        objects = split_objects(bucket, export_prefix, split)
        if not objects:
            raise FileNotFoundError(f"No Parquet files found for {split} in S3 export")
        files_by_split[split] = objects
        total_bytes += sum(int(item.get("Size", 0)) for item in objects)
    if total_bytes > MAX_EXPORT_BYTES:
        raise ValueError(
            f"Export is {total_bytes} bytes; Lambda limit is {MAX_EXPORT_BYTES} bytes"
        )

    with tempfile.TemporaryDirectory(prefix="sentinelpay-training-") as tmp_dir:
        input_root = Path(tmp_dir) / "input"
        output_dir = Path(tmp_dir) / "output"
        for split, objects in files_by_split.items():
            split_dir = input_root / f"dataset_split={split}"
            split_dir.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(objects):
                parquet_path = split_dir / f"part-{index:05d}.parquet"
                S3.download_file(bucket, item["Key"], str(parquet_path))
                validate_label_maturity(parquet_path)

        loaded = {split: load_split(input_root, split) for split in SPLITS}
        for split in SPLITS:
            _, labels, _ = loaded[split]
            if len(labels) != expected_rows[split]:
                raise ValueError(
                    f"{split} export has {len(labels)} rows; manifest reports "
                    f"{expected_rows[split]}"
                )

        results = train_loaded_splits(
            loaded,
            output_dir,
            minimum_fraud_rows_per_split=MINIMUM_FRAUD_ROWS,
        )
        results["training_metadata"] = {
            "export_id": run_id,
            "glue_run_id": run_id,
            "source_manifest_s3_uri": f"s3://{bucket}/{manifest_key}",
            "training_export_uri": f"s3://{bucket}/{export_prefix}",
            "trained_at_utc": datetime.now(timezone.utc).isoformat(),
            "minimum_label_delay_days": MINIMUM_LABEL_DELAY_DAYS,
            "minimum_fraud_rows_per_split": MINIMUM_FRAUD_ROWS,
        }
        metrics_path = output_dir / "metrics.json"
        metrics_path.write_text(json.dumps(results, indent=2) + "\n")

        S3.upload_file(
            str(output_dir / "logistic_regression_baseline.joblib"),
            bucket,
            model_key,
            ExtraArgs={"ContentType": "application/octet-stream", "ServerSideEncryption": "aws:kms"},
        )
        # Write metrics last; its presence is the idempotency/completion marker.
        S3.upload_file(
            str(metrics_path),
            bucket,
            metrics_key,
            ExtraArgs={"ContentType": "application/json", "ServerSideEncryption": "aws:kms"},
        )

    result = {
        "status": "TRAINED",
        "export_id": run_id,
        "model_uri": f"s3://{bucket}/{model_key}",
        "metrics_uri": f"s3://{bucket}/{metrics_key}",
        "split_rows": results["split_rows"],
        "test_metrics": results["test"],
    }
    LOGGER.info(json.dumps(result, sort_keys=True))
    return result


def process_record(record: dict[str, Any]) -> dict[str, Any]:
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])
    if not key.startswith(MANIFEST_PREFIX) or not key.endswith("manifest.json"):
        LOGGER.info("Ignoring object outside Glue manifest prefix: %s", key)
        return {"status": "IGNORED", "key": key}

    response = S3.get_object(Bucket=bucket, Key=key)
    with response["Body"] as body:
        manifest = json.loads(body.read())
    prepared = validate_manifest_export(manifest, bucket)
    if prepared is None:
        return {"status": "SKIPPED", "key": key}
    export_prefix, run_id, counts = prepared
    return train_export(bucket, key, manifest, export_prefix, run_id, counts)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    results = [process_record(record) for record in event.get("Records", [])]
    return {"processed_records": len(results), "results": results}

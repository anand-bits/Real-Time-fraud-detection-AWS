"""Start the SentinelPay Glue batch job from a completed raw S3 batch."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from urllib.parse import unquote_plus

import boto3


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

BUCKET = os.environ["BUCKET"]
GLUE_JOB_NAME = os.environ["GLUE_JOB_NAME"]
COMPLETION_KEY = re.compile(
    r"^raw/metadata/ingest_date=(\d{4}-\d{2}-\d{2})/"
    r"batch_id=([A-Za-z0-9_-]+)/batch_complete\.json$"
)
glue = boto3.client("glue")
s3 = boto3.client("s3")

ACTIVE_OR_FINISHED_STATES = {
    "STARTING", "WAITING", "RUNNING", "STOPPING", "SUCCEEDED"
}


def _read_batch_marker(key: str) -> tuple[str, str]:
    match = COMPLETION_KEY.fullmatch(key)
    if not match:
        raise ValueError(f"Unexpected raw batch completion key: {key}")

    ingest_date, batch_id = match.groups()
    date.fromisoformat(ingest_date)
    response = s3.get_object(Bucket=BUCKET, Key=key)
    try:
        marker = json.loads(response["Body"].read())
    finally:
        response["Body"].close()

    if (
        marker.get("manifest_version") != 1
        or marker.get("status") != "READY"
        or marker.get("ingest_date") != ingest_date
        or marker.get("batch_id") != batch_id
    ):
        raise ValueError(f"Completion marker does not match its S3 key: s3://{BUCKET}/{key}")
    return ingest_date, batch_id


def _existing_run(ingest_date: str, batch_id: str) -> dict | None:
    paginator = glue.get_paginator("get_job_runs")
    for page in paginator.paginate(JobName=GLUE_JOB_NAME, PaginationConfig={"PageSize": 100}):
        for run in page.get("JobRuns", []):
            arguments = run.get("Arguments", {})
            if (
                arguments.get("--ingest_date") == ingest_date
                and arguments.get("--batch_id") == batch_id
                and run.get("JobRunState") in ACTIVE_OR_FINISHED_STATES
            ):
                return run
    return None


def _start_for_record(record: dict) -> dict:
    bucket = record.get("s3", {}).get("bucket", {}).get("name")
    key = unquote_plus(record.get("s3", {}).get("object", {}).get("key", ""))
    if bucket != BUCKET:
        raise ValueError(f"Unexpected S3 bucket in event: {bucket}")

    ingest_date, batch_id = _read_batch_marker(key)
    existing = _existing_run(ingest_date, batch_id)
    if existing:
        LOGGER.info(
            "Skipping duplicate completion event; Glue run %s is %s for batch %s",
            existing["Id"], existing["JobRunState"], batch_id,
        )
        return {"batch_id": batch_id, "job_run_id": existing["Id"], "deduplicated": True}

    response = glue.start_job_run(
        JobName=GLUE_JOB_NAME,
        Arguments={"--ingest_date": ingest_date, "--batch_id": batch_id},
        JobRunQueuingEnabled=True,
    )
    run_id = response["JobRunId"]
    LOGGER.info("Started Glue run %s for batch %s (ingest date %s)", run_id, batch_id, ingest_date)
    return {"batch_id": batch_id, "job_run_id": run_id, "deduplicated": False}


def lambda_handler(event: dict, context: object) -> dict:
    """Handle S3 ObjectCreated notifications for batch completion markers."""
    results = [_start_for_record(record) for record in event.get("Records", [])]
    return {"started_or_found": results}

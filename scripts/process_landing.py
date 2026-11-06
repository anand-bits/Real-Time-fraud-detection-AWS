"""Validate and deduplicate a small S3 raw landing batch into clean JSONL."""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from jsonschema import Draft202012Validator, FormatChecker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--input-prefix", required=True)
    parser.add_argument(
        "--schema",
        default="data/contracts/payment-authorized.schema.json",
    )
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--output-prefix", default="clean/payments")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write clean output and manifest to S3. Without this, only report counts.",
    )
    return parser.parse_args()


def read_jsonl_gzip(s3: Any, bucket: str, key: str) -> list[dict[str, Any]]:
    response = s3.get_object(Bucket=bucket, Key=key)
    with response["Body"] as body:
        compressed = body.read()

    content = gzip.decompress(compressed).decode("utf-8")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{key}:{line_number}: expected a JSON object")
        records.append(value)
    return records


def main() -> int:
    args = parse_args()
    schema_path = Path(args.schema)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    keys = sorted(
        item["Key"]
        for page in paginator.paginate(Bucket=args.bucket, Prefix=args.input_prefix)
        for item in page.get("Contents", [])
        if item["Key"].endswith(".gz")
    )
    if not keys:
        print(f"No .gz objects found under s3://{args.bucket}/{args.input_prefix}", file=sys.stderr)
        return 2

    total_records = 0
    invalid_records: list[dict[str, Any]] = []
    unique_records: dict[str, dict[str, Any]] = {}
    duplicate_records = 0

    for key in keys:
        for line_number, record in enumerate(read_jsonl_gzip(s3, args.bucket, key), start=1):
            total_records += 1
            errors = sorted(validator.iter_errors(record), key=lambda err: list(err.path))
            if errors:
                invalid_records.append({
                    "source_key": key,
                    "record_number_in_object": line_number,
                    "errors": [error.message for error in errors],
                    "record": record,
                })
                continue

            event_id = record["event_id"]
            if event_id in unique_records:
                duplicate_records += 1
            else:
                unique_records[event_id] = record

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    run_date = now.strftime("%Y-%m-%d")
    destination = f"{args.output_prefix.rstrip('/')}/run_date={run_date}/run_id={run_id}"

    manifest = {
        "run_id": run_id,
        "created_at": now.isoformat(),
        "input_bucket": args.bucket,
        "input_prefix": args.input_prefix,
        "source_objects": keys,
        "schema": str(schema_path),
        "total_records": total_records,
        "valid_unique_records": len(unique_records),
        "invalid_records": len(invalid_records),
        "duplicate_records": duplicate_records,
        "data_classification": "SYNTHETIC",
    }

    print(json.dumps(manifest, indent=2))
    if not args.write:
        print("Dry run only. Re-run with --write to save the clean batch and manifest.")
        return 0

    clean_body = "".join(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        for record in unique_records.values()
    ).encode("utf-8")

    s3.put_object(
        Bucket=args.bucket,
        Key=f"{destination}/payments.jsonl",
        Body=clean_body,
        ContentType="application/x-ndjson",
    )
    s3.put_object(
        Bucket=args.bucket,
        Key=f"{destination}/manifest.json",
        Body=(json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
        ContentType="application/json",
    )
    if invalid_records:
        quarantine_body = "".join(
            json.dumps(item, separators=(",", ":"), sort_keys=True) + "\n"
            for item in invalid_records
        ).encode("utf-8")
        s3.put_object(
            Bucket=args.bucket,
            Key=f"{destination}/quarantine/invalid.jsonl",
            Body=quarantine_body,
            ContentType="application/x-ndjson",
        )

    print(f"Wrote {len(unique_records)} unique events to s3://{args.bucket}/{destination}/")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ClientError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Processing failed: {error}", file=sys.stderr)
        sys.exit(1)

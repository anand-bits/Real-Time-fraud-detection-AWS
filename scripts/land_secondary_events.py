"""Compress and upload synthetic feature updates and decisions to S3 raw."""
from __future__ import annotations

import argparse
import gzip
import re
import shutil
import sys
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


FILES = {
    "feature_updates.jsonl": "feature_updates",
    "fraud_decisions.jsonl": "fraud_decisions",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--ingest-date", required=True)
    parser.add_argument("--region", default="ap-southeast-2")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.batch_id):
        raise ValueError("batch-id may contain only letters, numbers, hyphens, and underscores")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.ingest_date):
        raise ValueError("ingest-date must use YYYY-MM-DD format")

    input_dir = Path(args.input_dir)
    missing = [name for name in FILES if not (input_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing generated files: {', '.join(missing)}")

    s3 = boto3.Session(region_name=args.region).client("s3")
    uploaded: list[str] = []

    with tempfile.TemporaryDirectory(prefix="sentinelpay-secondary-") as temp_dir:
        for filename, event_type in FILES.items():
            source = input_dir / filename
            compressed = Path(temp_dir) / f"{filename}.gz"
            with source.open("rb") as source_file, gzip.open(compressed, "wb") as gzip_file:
                shutil.copyfileobj(source_file, gzip_file)

            key = (
                f"raw/{event_type}/ingest_date={args.ingest_date}/"
                f"batch_id={args.batch_id}/{filename}.gz"
            )
            s3.upload_file(
                str(compressed),
                args.bucket,
                key,
                ExtraArgs={
                    "ContentType": "application/x-ndjson",
                    "ContentEncoding": "gzip",
                    "Metadata": {
                        "data-classification": "SYNTHETIC",
                        "batch-id": args.batch_id,
                    },
                },
            )
            uploaded.append(key)

    manifest_key = (
        f"raw/metadata/ingest_date={args.ingest_date}/"
        f"batch_id={args.batch_id}/secondary_events_manifest.json"
    )
    s3.upload_file(
        str(input_dir / "secondary_events_manifest.json"),
        args.bucket,
        manifest_key,
        ExtraArgs={
            "ContentType": "application/json",
            "Metadata": {
                "data-classification": "SYNTHETIC",
                "batch-id": args.batch_id,
            },
        },
    )
    uploaded.append(manifest_key)

    for key in uploaded:
        print(f"s3://{args.bucket}/{key}")
    print(f"Uploaded {len(uploaded)} objects.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ClientError, OSError, ValueError) as error:
        print(f"Landing failed: {error}", file=sys.stderr)
        sys.exit(1)

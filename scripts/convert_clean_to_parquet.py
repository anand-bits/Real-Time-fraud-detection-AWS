"""Convert a validated clean payments JSONL object in S3 to typed Parquet."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError


PAYMENT_SCHEMA = pa.schema([
    pa.field("data_classification", pa.string(), nullable=False),
    pa.field("schema_version", pa.int32(), nullable=False),
    pa.field("event_id", pa.string(), nullable=False),
    pa.field("payment_id", pa.string(), nullable=False),
    pa.field("idempotency_key", pa.string(), nullable=False),
    pa.field("event_time", pa.string(), nullable=False),
    pa.field("received_at", pa.string(), nullable=False),
    pa.field("payment_token", pa.string(), nullable=False),
    pa.field("account_token", pa.string(), nullable=False),
    pa.field("merchant_id", pa.string(), nullable=False),
    pa.field("device_token", pa.string(), nullable=False),
    pa.field("amount", pa.float64(), nullable=False),
    pa.field("currency", pa.string(), nullable=False),
    pa.field("channel", pa.string(), nullable=False),
    pa.field("country_code", pa.string(), nullable=False),
    pa.field("device_first_seen_days", pa.int32(), nullable=False),
    pa.field("source_region", pa.string(), nullable=False),
    pa.field("trace_id", pa.string(), nullable=False),
])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--input-key", required=True)
    parser.add_argument("--run-date", required=True, help="Partition date, YYYY-MM-DD")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--region", default="ap-southeast-2")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")

    response = s3.get_object(Bucket=args.bucket, Key=args.input_key)
    with response["Body"] as body:
        lines = body.read().decode("utf-8").splitlines()

    records = [json.loads(line) for line in lines if line.strip()]
    if not records:
        raise ValueError("Input JSONL object contains no records")

    table = pa.Table.from_pylist(records, schema=PAYMENT_SCHEMA)
    buffer = pa.BufferOutputStream()
    pq.write_table(table, buffer, compression="snappy")

    output_key = (
        f"curated/parquet/payments/run_date={args.run_date}/"
        f"run_id={args.run_id}/part-00000.parquet"
    )
    s3.put_object(
        Bucket=args.bucket,
        Key=output_key,
        Body=buffer.getvalue().to_pybytes(),
        ContentType="application/vnd.apache.parquet",
    )

    print(f"rows={table.num_rows}")
    print(f"columns={table.num_columns}")
    print(f"output=s3://{args.bucket}/{output_key}")
    print(f"schema={table.schema}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ClientError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        sys.exit(1)

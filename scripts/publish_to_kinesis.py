#!/usr/bin/env python3
"""Publish synthetic payment events to the SentinelPay Kinesis stream."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

MAX_RECORDS_PER_REQUEST = 500


def load_records(path: Path, limit: int, region: str) -> list[dict[str, Any]]:
    records = []

    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue

            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"Line {line_number} is not a JSON object.")
            if event.get("data_classification") != "SYNTHETIC":
                raise ValueError(f"Line {line_number} is not marked SYNTHETIC.")
            if event.get("source_region") != region:
                raise ValueError(
                    f"Line {line_number} has source_region "
                    f"{event.get('source_region')!r}; expected {region!r}."
                )

            account_token = event.get("account_token")
            if not account_token or not event.get("payment_id"):
                raise ValueError(f"Line {line_number} lacks payment_id or account_token.")

            payload = json.dumps(
                event, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")

            records.append({
                "Data": payload,
                "PartitionKey": account_token,
            })

            if len(records) >= limit:
                break

    if not records:
        raise ValueError(f"No payment events found in {path}.")

    return records


def publish_records(
    client: Any, stream_name: str, records: list[dict[str, Any]]
) -> int:
    sent_count = 0

    for offset in range(0, len(records), MAX_RECORDS_PER_REQUEST):
        pending = records[offset:offset + MAX_RECORDS_PER_REQUEST]

        for attempt in range(5):
            response = client.put_records(
                StreamName=stream_name,
                Records=pending,
            )

            results = response["Records"]
            failed = [
                record
                for record, result in zip(pending, results)
                if result.get("ErrorCode")
            ]
            sent_count += len(pending) - len(failed)

            if not failed:
                break

            if attempt == 4:
                details = [
                    result.get("ErrorCode")
                    for result in results
                    if result.get("ErrorCode")
                ]
                raise RuntimeError(
                    f"{len(failed)} records still failed after retries: {details}"
                )

            time.sleep(min(2**attempt, 8) + random.uniform(0, 0.25))
            pending = failed

    return sent_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("work/synthetic/step3-smoke/payment_authorized.jsonl"),
    )
    parser.add_argument("--stream-name", default="sentinelpay-payments-dev")
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--limit", type=int, default=21)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually send records to Kinesis; without this flag, only preview.",
    )
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")

    try:
        records = load_records(args.file, args.limit, args.region)

        if not args.publish:
            print(
                f"Dry run: {len(records)} synthetic events are ready for "
                f"{args.stream_name} in {args.region}."
            )
            return 0

        client = boto3.Session(region_name=args.region).client("kinesis")
        sent_count = publish_records(client, args.stream_name, records)
        print(f"Published {sent_count} of {len(records)} events to Kinesis.")
        return 0
    except (ClientError, RuntimeError, ValueError) as error:
        print(f"Publisher failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
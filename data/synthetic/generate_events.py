#!/usr/bin/env python3
"""Deterministically generate tokenized SentinelPay events for local development."""
from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

NAMESPACE = uuid.UUID("2b6db48e-8cd2-4bc3-a2b7-9e2c80892348")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("base-time must include a timezone, such as Z")
    return parsed.astimezone(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def stable_id(prefix: str, seed: int, index: int) -> str:
    return f"{prefix}_{uuid.uuid5(NAMESPACE, f'{seed}:{prefix}:{index}').hex[:16]}"


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def build_events(count: int, seed: int, base: datetime, source_region: str,
                 duplicate_rate: float, late_rate: float, label_delay_days: int
                 ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    payments: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    fraud_count = 0
    late_count = 0

    for index in range(count):
        payment_id = f"pay_{index + 1:08d}"
        fraud = rng.random() < 0.10
        fraud_count += int(fraud)

        # Signals overlap: some legitimate payments look risky and some fraud is subtle.
        new_device = rng.random() < (0.62 if fraud else 0.14)
        high_amount = rng.random() < (0.58 if fraud else 0.11)
        risky_merchant = rng.random() < (0.29 if fraud else 0.07)
        amount = round(rng.uniform(350.0, 2500.0) if high_amount else rng.uniform(4.0, 220.0), 2)
        device_age = 0 if new_device else rng.randint(2, 720)

        # A few account keys are intentionally hot for skew tests.
        if index % 9 == 0:
            account_index = index % 4
        else:
            account_index = rng.randrange(max(count, 1))
        account_token = f"atok_{account_index + 1:06d}"
        device_index = (index % 45) if new_device else rng.randrange(max(count, 1))
        merchant_index = rng.randrange(1, 5) if risky_merchant else rng.randrange(5, 31)

        arrival = base + timedelta(seconds=index * 7 + 2)
        event_time = arrival - timedelta(seconds=2)
        if rng.random() < late_rate:
            event_time = arrival - timedelta(minutes=rng.randint(5, 120))
            late_count += 1

        trace = uuid.uuid5(NAMESPACE, f"{seed}:trace:{index}").hex
        payment = {
            "data_classification": "SYNTHETIC",
            "schema_version": 1,
            "event_id": stable_id("evt", seed, index),
            "payment_id": payment_id,
            "idempotency_key": stable_id("idem", seed, index),
            "event_time": stamp(event_time),
            "received_at": stamp(arrival),
            "payment_token": f"ptok_{(index % 500) + 1:06d}",
            "account_token": account_token,
            "merchant_id": f"mer_{merchant_index:04d}",
            "device_token": f"dtok_{device_index + 1:06d}",
            "amount": amount,
            "currency": rng.choice(["USD", "EUR", "GBP"]),
            "channel": "CARD_NOT_PRESENT",
            "country_code": rng.choice(["US", "GB", "DE", "IN", "SG"]),
            "device_first_seen_days": device_age,
            "source_region": source_region,
            "trace_id": trace,
        }
        payments.append(payment)

        observed = event_time + timedelta(days=label_delay_days)
        outcomes.append({
            "data_classification": "SYNTHETIC",
            "schema_version": 1,
            "outcome_event_id": stable_id("out", seed, index),
            "payment_id": payment_id,
            "outcome": "CONFIRMED_FRAUD" if fraud else "NO_FRAUD",
            "outcome_source": "SYNTHETIC_LABEL_GENERATOR",
            "payment_event_time": stamp(event_time),
            "label_observed_at": stamp(observed),
            "source_region": source_region,
            "trace_id": trace,
        })

    duplicate_count = int(round(count * duplicate_rate))
    if count and duplicate_rate > 0 and duplicate_count == 0:
        duplicate_count = 1
    duplicates = [dict(record) for record in rng.sample(payments, min(duplicate_count, count))]
    delivered = payments + duplicates
    rng.shuffle(delivered)
    rng.shuffle(outcomes)

    invalid: list[dict[str, Any]] = []
    if payments:
        missing = dict(payments[0])
        missing.pop("payment_token")
        invalid.append(missing)
        negative = dict(payments[0])
        negative["event_id"] = stable_id("evt", seed, count + 1)
        negative["payment_id"] = f"pay_{count + 1:08d}"
        negative["idempotency_key"] = stable_id("idem", seed, count + 1)
        negative["amount"] = -5.0
        invalid.append(negative)
        bad_country = dict(payments[0])
        bad_country["event_id"] = stable_id("evt", seed, count + 2)
        bad_country["payment_id"] = f"pay_{count + 2:08d}"
        bad_country["idempotency_key"] = stable_id("idem", seed, count + 2)
        bad_country["country_code"] = "USA"
        invalid.append(bad_country)

    manifest = {
        "data_classification": "SYNTHETIC",
        "generator_version": 1,
        "seed": seed,
        "base_time": stamp(base),
        "source_region": source_region,
        "unique_payment_count": count,
        "delivered_payment_record_count": len(delivered),
        "duplicate_record_count": len(duplicates),
        "simulated_fraud_count": fraud_count,
        "late_event_count": late_count,
        "label_delay_days": label_delay_days,
        "duplicate_rate": duplicate_rate,
        "late_rate": late_rate,
    }
    return delivered, outcomes, invalid, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=21)
    parser.add_argument("--base-time", default="2026-01-01T00:00:00Z")
    parser.add_argument("--source-region", default="us-east-1")
    parser.add_argument("--duplicate-rate", type=float, default=0.02)
    parser.add_argument("--late-rate", type=float, default=0.05)
    parser.add_argument("--label-delay-days", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("work/synthetic"))
    args = parser.parse_args()

    if args.events < 0:
        parser.error("--events must be non-negative")
    if not 0 <= args.duplicate_rate <= 1 or not 0 <= args.late_rate <= 1:
        parser.error("duplicate and late rates must be between 0 and 1")
    if args.label_delay_days < 0:
        parser.error("--label-delay-days must be non-negative")
    try:
        base = parse_time(args.base_time)
    except ValueError as exc:
        parser.error(str(exc))

    args.output.mkdir(parents=True, exist_ok=True)
    payments, outcomes, invalid, manifest = build_events(
        args.events, args.seed, base, args.source_region,
        args.duplicate_rate, args.late_rate, args.label_delay_days,
    )
    write_jsonl(args.output / "payment_authorized.jsonl", payments)
    write_jsonl(args.output / "chargeback_outcomes.jsonl", outcomes)
    write_jsonl(args.output / "intentionally_invalid_payments.jsonl", invalid)
    (args.output / "generation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(payments)} payment deliveries ({manifest['duplicate_record_count']} duplicates), "
          f"{len(outcomes)} delayed outcomes, and {len(invalid)} invalid examples to {args.output}")


if __name__ == "__main__":
    main()

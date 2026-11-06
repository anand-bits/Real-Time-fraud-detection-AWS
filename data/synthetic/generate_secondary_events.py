"""Generate point-in-time synthetic feature snapshots and rules decisions."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payments", required=True)
    parser.add_argument("--contracts-dir", default="data/contracts")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    contracts = Path(args.contracts_dir)
    feature_schema = json.loads((contracts / "feature-update.schema.json").read_text())
    decision_schema = json.loads((contracts / "fraud-decision.schema.json").read_text())
    feature_validator = Draft202012Validator(feature_schema, format_checker=FormatChecker())
    decision_validator = Draft202012Validator(decision_schema, format_checker=FormatChecker())

    delivered = read_jsonl(Path(args.payments))
    unique: dict[str, dict[str, Any]] = {}
    for payment in delivered:
        unique.setdefault(payment["event_id"], payment)

    payments = sorted(
        unique.values(),
        key=lambda row: (parse_time(row["event_time"]), row["event_id"]),
    )

    account_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    features: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    for payment in payments:
        event_time = parse_time(payment["event_time"])
        received_at = parse_time(payment["received_at"])
        window_start = event_time - timedelta(hours=1)
        account = payment["account_token"]

        prior = [
            row for row in account_history[account]
            if window_start <= parse_time(row["event_time"]) < event_time
            and parse_time(row["received_at"]) <= received_at
            and row["currency"] == payment["currency"]
        ]

        prior_devices = {
            row["device_token"] for row in prior
            if row["device_first_seen_days"] == 0
        }
        feature_time = received_at + timedelta(milliseconds=20)
        decision_time = received_at + timedelta(milliseconds=120)

        feature = {
            "data_classification": "SYNTHETIC",
            "schema_version": 1,
            "feature_event_id": "feat_" + payment["event_id"][4:],
            "entity_type": "ACCOUNT",
            "entity_token": account,
            "feature_version": 1,
            "window_start": format_time(window_start),
            "window_end": format_time(event_time),
            "window_seconds": 3600,
            "transaction_count": len(prior),
            "amount_sum": round(sum(float(row["amount"]) for row in prior), 2),
            "currency": payment["currency"],
            "distinct_merchant_count": len({row["merchant_id"] for row in prior}),
            "new_device_count": len(prior_devices),
            "computed_at": format_time(feature_time),
            "source_region": payment["source_region"],
        }

        risk_score = 0.05
        reasons: list[str] = []

        if float(payment["amount"]) >= 1000:
            risk_score += 0.35
            reasons.append("HIGH_AMOUNT")
        if payment["device_first_seen_days"] == 0:
            risk_score += 0.20
            reasons.append("NEW_DEVICE")
        if len(prior) >= 3:
            risk_score += 0.25
            reasons.append("VELOCITY_1H")
        if len({row["merchant_id"] for row in prior}) >= 3:
            risk_score += 0.15
            reasons.append("MERCHANT_BREADTH")
        if not reasons:
            reasons.append("BASELINE_LOW_RISK")

        risk_score = min(round(risk_score, 4), 0.99)
        if risk_score >= 0.85:
            action = "DECLINE"
        elif risk_score >= 0.65:
            action = "REVIEW"
        elif risk_score >= 0.40:
            action = "STEP_UP"
        else:
            action = "APPROVE"

        decision = {
            "data_classification": "SYNTHETIC",
            "schema_version": 1,
            "decision_id": "dec_" + payment["event_id"][4:],
            "event_id": payment["event_id"],
            "payment_id": payment["payment_id"],
            "decision": action,
            "risk_score": risk_score,
            "reason_codes": reasons,
            "model_id": "sentinelpay-rules",
            "model_version": "synthetic-rules-v1",
            "policy_version": "policy-v1",
            "feature_age_ms": 100,
            "fallback_used": False,
            "decision_time": format_time(decision_time),
            "source_region": payment["source_region"],
            "trace_id": payment["trace_id"],
        }

        if not feature_validator.is_valid(feature):
            raise ValueError(f"Generated feature failed its contract: {feature}")
        if not decision_validator.is_valid(decision):
            raise ValueError(f"Generated decision failed its contract: {decision}")

        features.append(feature)
        decisions.append(decision)
        account_history[account].append(payment)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "feature_updates.jsonl", features)
    write_jsonl(output_dir / "fraud_decisions.jsonl", decisions)

    manifest = {
        "data_classification": "SYNTHETIC",
        "unique_payment_count": len(payments),
        "feature_update_count": len(features),
        "fraud_decision_count": len(decisions),
        "decision_type": "deterministic synthetic rules; not an ML prediction",
    }
    (output_dir / "secondary_events_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Generation failed: {error}", file=sys.stderr)
        sys.exit(1)

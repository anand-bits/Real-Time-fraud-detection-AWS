"""Contract and generator checks; install requirements-dev before running."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "data" / "contracts"
EXAMPLES = CONTRACTS / "examples"
GENERATOR = ROOT / "data" / "synthetic" / "generate_events.py"


class ContractTests(unittest.TestCase):
    def test_examples_validate_and_schemas_are_well_formed(self):
        for schema_path in sorted(CONTRACTS.glob("*.schema.json")):
            schema = json.loads(schema_path.read_text())
            Draft202012Validator.check_schema(schema)
            example_path = EXAMPLES / schema_path.name.replace(".schema.json", ".example.json")
            example = json.loads(example_path.read_text())
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)

    def test_generator_outputs_valid_contract_events_and_invalid_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "generated"
            subprocess.run([
                sys.executable, str(GENERATOR), "--events", "80", "--seed", "7",
                "--output", str(out),
            ], check=True, capture_output=True, text=True)

            payment_schema = json.loads((CONTRACTS / "payment-authorized.schema.json").read_text())
            outcome_schema = json.loads((CONTRACTS / "chargeback-outcome.schema.json").read_text())
            payment_validator = Draft202012Validator(payment_schema, format_checker=FormatChecker())
            outcome_validator = Draft202012Validator(outcome_schema, format_checker=FormatChecker())

            payments = [json.loads(line) for line in (out / "payment_authorized.jsonl").read_text().splitlines()]
            outcomes = [json.loads(line) for line in (out / "chargeback_outcomes.jsonl").read_text().splitlines()]
            invalid = [json.loads(line) for line in (out / "intentionally_invalid_payments.jsonl").read_text().splitlines()]
            manifest = json.loads((out / "generation_manifest.json").read_text())

            self.assertEqual(len(payments), manifest["delivered_payment_record_count"])
            self.assertEqual(len(outcomes), 80)
            self.assertGreater(manifest["duplicate_record_count"], 0)
            self.assertGreater(manifest["late_event_count"], 0)
            self.assertTrue(all(payment_validator.is_valid(record) for record in payments))
            self.assertTrue(all(outcome_validator.is_valid(record) for record in outcomes))
            self.assertTrue(all(not payment_validator.is_valid(record) for record in invalid))

            by_payment = {row["payment_id"]: row for row in outcomes}
            for event in payments:
                payment_time = datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
                label_time = datetime.fromisoformat(by_payment[event["payment_id"]]["label_observed_at"].replace("Z", "+00:00"))
                self.assertEqual((label_time - payment_time).days, 30)
                self.assertNotIn("outcome", event)


if __name__ == "__main__":
    unittest.main()

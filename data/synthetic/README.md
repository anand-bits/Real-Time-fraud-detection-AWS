# Synthetic event generator

Run from the repository root:

    python3 data/synthetic/generate_events.py --events 1000 --output work/synthetic

The generator uses only the Python standard library. The same seed, base time, event count, and options produce the same records.

Outputs:
- payment_authorized.jsonl: valid synthetic authorizations; some IDs are deliberately duplicated and the records are shuffled.
- chargeback_outcomes.jsonl: one delayed synthetic label per unique payment. Labels are not embedded in payment events.
- intentionally_invalid_payments.jsonl: examples with a missing required field, negative amount, or invalid country code. These are expected to fail contract validation.
- generation_manifest.json: seed and generation parameters; no current clock time is included.

Defaults use a 10% latent fraud rate, a 30-day simulated label delay, a small duplicate rate, and late event timestamps. Risk indicators overlap between legitimate and fraudulent payments so the label is not determined by one trivial field. All tokens and identities are fake.

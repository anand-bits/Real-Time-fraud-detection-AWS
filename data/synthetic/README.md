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

## Recreate the current three-batch dataset

Run these from the repository root. The seeds and base times reproduce the initial training, validation, and test batches used in the current project. Payment labels are delayed by 30 days and kept in a separate file.

```sh
python data/synthetic/generate_events.py --events 10000 --seed 7 --base-time 2026-01-01T00:00:00Z --output work/synthetic/bronze-10k
python data/synthetic/generate_secondary_events.py --payments work/synthetic/bronze-10k/payment_authorized.jsonl --contracts-dir data/contracts --output-dir work/synthetic/bronze-10k

python data/synthetic/generate_events.py --events 1500 --seed 17 --base-time 2026-06-01T00:00:00Z --output work/synthetic/validation-1500
python data/synthetic/generate_secondary_events.py --payments work/synthetic/validation-1500/payment_authorized.jsonl --contracts-dir data/contracts --output-dir work/synthetic/validation-1500

python data/synthetic/generate_events.py --events 1500 --seed 29 --base-time 2026-09-01T00:00:00Z --output work/synthetic/test-1500
python data/synthetic/generate_secondary_events.py --payments work/synthetic/test-1500/payment_authorized.jsonl --contracts-dir data/contracts --output-dir work/synthetic/test-1500
```

The event generator writes payment authorizations, chargeback outcomes, intentionally invalid fixtures, and a generation manifest. The secondary generator adds feature updates, deterministic fraud decisions, and its manifest. These decisions are synthetic rules outputs, not model predictions. Re-running a command overwrites files in its output directory; copy any local edits before regenerating.

## Land the batches in S3

The landing commands are in the end-to-end [data workflow runbook](../../docs/runbooks/current-data-workflow.md). They upload to `raw/` and replace objects with the same batch ID and ingest date. Use a new batch ID when you intend to preserve a new independent ingestion run. Never point the generator or landing scripts at real payment data.

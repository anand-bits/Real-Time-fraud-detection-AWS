# SentinelPay current data workflow

This runbook records the working synthetic-data path built so far. It is for a personal portfolio and learning account. It is not a production payment system. Use synthetic data only.

## What is implemented

| Layer | Current implementation | Verification evidence from the completed run |
|---|---|---|
| Raw | S3 `raw/` prefixes; batch JSONL compressed to gzip; streaming payments delivered by Firehose | Three historical batches and a 21-record Kinesis smoke batch landed |
| Bronze | Athena external tables `payments_bronze`, `feature_updates_bronze`, `fraud_decisions_bronze`, `chargeback_outcomes_bronze` | Per-batch counts and duplicate delivery counts reconciled |
| Silver | Athena Iceberg tables with deduplication and batch-aware identifiers | Historical data has 13,000 unique payment identities; stream replay matched existing events |
| Gold | `training_examples_gold`, `fraud_daily_metrics_gold`, and `pipeline_audit` | Training examples: 13,000; splits: 10,031 / 1,494 / 1,475 |
| Baseline ML | Local scikit-learn Logistic Regression trained from Athena Parquet export | Metrics and model saved under `work/ml/baseline/` |

The ordered Athena SQL is saved under `sql/athena/`, from external Bronze table creation through Silver merges, Gold creation/population, and audit reconciliation. It uses the existing database name, event contracts, batch IDs, and S3 layout. Check the SQL guide before running it in another account.

## 1. Local prerequisites

Run from the repository root. Use a Python virtual environment and install the pinned project dependencies. Configure AWS CLI credentials locally; do not paste secrets into chat or commit credentials.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests/contract -v
aws sts get-caller-identity
aws configure get region
```

Expected region for the current sandbox: `ap-southeast-2`. The contract suite checks schemas and generator output locally; it does not contact AWS.

## 2. Recreate the historical synthetic batches

Use the deterministic commands in [data/synthetic/README.md](../../data/synthetic/README.md). They create a 10,000-payment training batch and separate 1,500-payment validation and test batches. Each batch contains payment deliveries (including deliberate duplicates), delayed outcomes, invalid test fixtures, and generated secondary feature/decision events.

The synthetic fraud decisions are deterministic rules output. They are included as a data source for the pipeline, not as predictions from the trained baseline model.

## 3. Land batches in S3 raw

Current example bucket: `sentinelpay-raw-dev-908768512617-ap-southeast-2`. Example ingestion date: `2026-11-04`. Replace these values if using another account, bucket, or date. The batch ID is part of the S3 key; rerunning with the same batch ID and ingest date overwrites those same objects.

```sh
BUCKET=sentinelpay-raw-dev-908768512617-ap-southeast-2
REGION=ap-southeast-2
INGEST_DATE=2026-11-04

python scripts/land_synthetic_batch.py --input-dir work/synthetic/bronze-10k --bucket "$BUCKET" --batch-id bronze-10k-seed7-20261104 --ingest-date "$INGEST_DATE" --region "$REGION"
python scripts/land_secondary_events.py --input-dir work/synthetic/bronze-10k --bucket "$BUCKET" --batch-id bronze-10k-seed7-20261104 --ingest-date "$INGEST_DATE" --region "$REGION"

python scripts/land_synthetic_batch.py --input-dir work/synthetic/validation-1500 --bucket "$BUCKET" --batch-id validation-1500-seed17-20260601 --ingest-date "$INGEST_DATE" --region "$REGION"
python scripts/land_secondary_events.py --input-dir work/synthetic/validation-1500 --bucket "$BUCKET" --batch-id validation-1500-seed17-20260601 --ingest-date "$INGEST_DATE" --region "$REGION"

python scripts/land_synthetic_batch.py --input-dir work/synthetic/test-1500 --bucket "$BUCKET" --batch-id test-1500-seed29-20260901 --ingest-date "$INGEST_DATE" --region "$REGION"
python scripts/land_secondary_events.py --input-dir work/synthetic/test-1500 --bucket "$BUCKET" --batch-id test-1500-seed29-20260901 --ingest-date "$INGEST_DATE" --region "$REGION"
```

The two landing scripts each upload data and a manifest. The intentionally invalid payment fixtures land under `raw/test_fixtures/`; they must not be mixed into the valid payment table.

## 4. Raw-to-clean smoke path

This smaller path validates a Firehose delivery without consuming the historical batches. It reads gzip objects from S3, validates the payment contract, counts duplicates, and writes a clean JSONL object plus manifest. Use an actual raw date prefix that exists in the bucket.

```sh
python scripts/process_landing.py \
  --bucket "$BUCKET" \
  --input-prefix raw/payments/ingest_date=2026-11-04/batch_id=streaming/ \
  --region "$REGION" \
  --write
```

The script writes to `clean/payments/run_date=.../run_id=.../`. To make Parquet for the one-file smoke flow:

```sh
python scripts/convert_clean_to_parquet.py \
  --bucket "$BUCKET" \
  --input-key clean/payments/run_date=2026-11-04/run_id=<run-id>/payments.jsonl \
  --run-date 2026-11-04 \
  --run-id <run-id> \
  --region "$REGION"
```

This clean-path Parquet output is a separate smoke artifact. The main Bronze/Silver/Gold training path reads the partitioned raw batch families through Athena.

## 5. Athena Bronze, Silver, Gold, and audit

Select the Athena workgroup and database `sentinelpay`. Run the saved SQL in [`sql/athena/`](../../sql/athena/README.md) in its listed order:

1. Bronze counts and uniqueness by batch.
2. Silver counts and key uniqueness by event family.
3. Gold split counts, label totals, and date span.
4. Audit status by batch and event type.
5. Export the Gold training examples to a new S3 prefix.

These SQL files reproduce the lakehouse steps. Existing tables created earlier with `IF NOT EXISTS` will remain as-is; use a clean database for a full rebuild. Compare `SHOW CREATE TABLE` output against the files before applying changes to existing tables.

## 6. Export and train the baseline

Use [`sql/athena/08_export_training_examples.sql`](../../sql/athena/08_export_training_examples.sql) with a fresh `export_id` destination. Athena `UNLOAD` needs an empty/nonexistent destination prefix. Download the three `dataset_split=...` folders from that exact export to `work/ml/training-export/` (or pass a different directory to the trainer), then run:

```sh
python ml/train_baseline.py --input-dir work/ml/training-export --output-dir work/ml/baseline
```

The trainer rejects overlapping payment IDs across splits, selects the probability threshold on validation only, and reports final test metrics without fitting on the test set. The model is intentionally a baseline; the focus of the project remains data engineering.

## 7. Streaming smoke test

The current Kinesis publisher defaults to a dry run. First confirm Firehose is `ACTIVE`, then explicitly publish the small generated smoke sample only when you intend to incur streaming charges:

```sh
python scripts/publish_to_kinesis.py
python scripts/publish_to_kinesis.py --publish
```

The publisher has a configurable `--limit` (default 21). Confirm newly delivered raw objects, run the Bronze-to-Silver streaming handling, and use the saved Athena queries to verify the event IDs. The prior smoke result was 21 records, 20 distinct event IDs, and a `PASS_WITH_DEDUP` audit result; replay matched all 20 distinct events already in Silver.

Stop any browser-based Firehose demo producer after testing. Do not delete raw S3 objects as part of this runbook. Pause or tear down billable resources only after checking Terraform state and the project's teardown notes.

## 8. Infrastructure and cost boundary

Terraform files live in `infra/terraform/`. Terraform state is local and ignored by Git; do not commit it. The existing S3, Kinesis, and Firehose resources are real AWS resources. Validate and inspect a Terraform plan before applying; apply only when you intend to make the displayed AWS changes. Kinesis and Firehose can incur usage charges even for small demos.

The full architecture's multi-Region, Flink, serving, Redshift, and managed model lifecycle components are not implied by the current workflow. Keep them optional until separately implemented and measured.

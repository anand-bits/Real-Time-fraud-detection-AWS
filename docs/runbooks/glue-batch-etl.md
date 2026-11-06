# Glue Spark batch processing

This is the automated batch implementation for SentinelPay. An S3 event on the completed raw batch marker starts the single-batch Glue job. A successful Glue completion manifest then triggers the model-training Lambda and its downstream SageMaker registration pipeline. Glue performs the transformations and split export; the Lambda trains/evaluates the model. SageMaker manages comparison and registration only. This path does not create a SageMaker training job or model endpoint.

## Data flow

1. Read the requested `ingest_date` and `batch_id` from raw S3 prefixes. The job reads raw JSONL directly instead of relying on typed Bronze rows so malformed input can be preserved for quarantine. The Bronze Athena tables remain the queryable view over the same raw objects.
2. Parse each event family using the v1 contracts in `data/contracts/`. Quarantine malformed or invalid rows under `quarantine/records/` with the raw JSON, source object, and validation errors.
3. Deduplicate valid records by their event/business key and use Iceberg `MERGE` to update or insert into the existing Silver tables.
4. Recompute the matured-label/point-in-time Gold source from the combined Silver tables, merge into the existing Gold training and daily metrics tables, and export the current train/validation/test dataset to a run-specific Parquet prefix.
5. Upsert per-batch counts and status into `sentinelpay.pipeline_audit`. Write a detailed per-run manifest, including quarantine and Gold counts, under `ops/glue_batch_runs/`.

Missing event families are recorded as `NO_DATA` and skipped. That supports separate arrivals such as payments today and matured chargeback outcomes later. If an event family is present but exceeds the configured invalid-record fraction, the job records `FAIL` and fails the Glue run. The default threshold is 5%; quarantined rows remain outside Silver.

## Prerequisites

The project S3 bucket and `sentinelpay` Glue Data Catalog database must already exist. The following tables must also exist with the schemas represented in `sql/athena/`:

- Bronze external tables: `payments_bronze`, `feature_updates_bronze`, `fraud_decisions_bronze`, `chargeback_outcomes_bronze`.
- Silver Iceberg tables: `payments_iceberg`, `feature_updates_iceberg`, `fraud_decisions_iceberg`, `chargeback_outcomes_iceberg`.
- Gold Iceberg tables: `training_examples_gold`, `fraud_daily_metrics_gold`.
- Audit Iceberg table: `pipeline_audit`.

The job uses AWS Glue 5.0 and its bundled Iceberg support. It runs with two `G.1X` workers, one concurrent run, a 45-minute timeout, and no automatic retries. It uses the existing S3 KMS key and writes no data outside the project bucket.

## Deploy the job definition

The Terraform files upload the script to `artifacts/glue/`, create a dedicated IAM role, and define the Glue job. They do not start the job. Run from the repository root:

```sh
terraform -chdir=infra/terraform fmt
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan
```

Review the plan before applying. The Kinesis and Firehose Terraform files are currently `.tf.paused`; Terraform will plan to remove those resources from state while creating the Glue job. Confirm the plan leaves the raw S3 bucket and its objects untouched. Do not apply a plan that proposes deleting the bucket.

## Automatically start a batch from its completion marker

Use `scripts/land_complete_batch.py` to upload all four event families. It writes `raw/metadata/ingest_date=<date>/batch_id=<batch>/batch_complete.json` only after all data objects and source manifests have been uploaded. S3 invokes `sentinelpay-glue-starter-dev` for that marker, and the starter starts Glue with the marker's `ingest_date` and `batch_id`.

For data uploaded manually in the S3 console, upload all event objects first, then upload a JSON marker at that exact path, for example:

```json
{"manifest_version":1,"status":"READY","ingest_date":"2026-11-06","batch_id":"my-historic-batch"}
```

The marker path and body values must match. Uploading data objects without this final marker does not start Glue, because S3 cannot determine when a multi-file batch is complete.

## Start one batch manually

After the Glue job is deployed, start one completed batch. This example uses the existing historical 10k batch and the current S3 ingest date:

```sh
aws glue start-job-run \
  --job-name sentinelpay-batch-etl-dev \
  --arguments '{"--ingest_date":"2026-11-04","--batch_id":"bronze-10k-seed7-20261104"}' \
  --region ap-southeast-2
```

The job arguments for bucket, database, quarantine prefix, Gold export prefix, split cutoffs, and invalid-record threshold are set in Terraform. `ingest_date` and `batch_id` are required for each run.

## Outputs and reruns

- Quarantine: `s3://<bucket>/quarantine/records/run_id=<glue-run-id>/`.
- Detailed run manifest: `s3://<bucket>/ops/glue_batch_runs/ingest_date=<date>/batch_id=<batch>/run_id=<glue-run-id>/manifest.json`.
- Gold training export: `s3://<bucket>/ml/training_exports/glue/export_id=<glue-run-id>/dataset_split=.../`.
- Summary audit: rows keyed by `ingest_date`, `batch_id`, and `event_type` in `pipeline_audit`.

Silver, Gold, and audit writes use Iceberg `MERGE`, so replaying the same event IDs updates matching rows instead of appending duplicate keys. Each execution writes a separate quarantine/run manifest/export prefix. Raw objects are never deleted or rewritten by this job.

### Verified run (2026-11-06)

Glue run `jr_9a1861325cb865d59cd245cd5b8cb913e8a06de8299305f26df3e6d417c2a6aa` completed with `SUCCEEDED` for `ingest_date=2026-11-04`, `batch_id=bronze-10k-seed7-20261104` in 169 seconds. The run manifest is under the path above. Payments reconciled 10,200 deliveries to 10,000 unique events with 200 duplicates (`PASS_WITH_DEDUP`); each of feature updates, fraud decisions, and chargeback outcomes processed 10,000 records with no duplicates or quarantines (`PASS`). Gold contained 13,000 training rows split into 10,031 train, 1,494 validation, and 1,475 test rows. The run-specific Parquet export exists at the corresponding `training_export_uri` in the manifest.

Athena confirmed the four audit rows and returned no payment IDs shared across dataset splits. This run also fixed four implementation gaps found during execution: the script now reads Glue's reserved run ID without registering it twice, merges against the existing Silver table schemas, materializes deduplicated sources before Iceberg `MERGE`, and applies shared validation checks only to fields present in each event contract. The job role policy now covers the actual `curated/iceberg/` and `ops/` table locations.

Synthetic generated payment IDs start at `pay_00000001` in every cohort. Glue namespaces payment, decision, label, and account identifiers by batch for every synthetic batch except the original seed-7 training cohort, which is already stored unnamespaced in Silver. This keeps cross-family joins aligned and prevents separate cohorts from producing duplicate Gold matches. Real records are not namespaced.

The Glue job exports Gold data but does not train the Logistic Regression model itself. Its successful run manifest triggers the model-training Lambda described in [the model-training and registration runbook](model-training-lambda.md). The Lambda trains/evaluates, then starts SageMaker Pipelines to register only a higher TEST ROC-AUC version. Registered packages require owner approval and are not automatically deployed. The current date split cutoffs are for the existing historic cohort; version new temporal boundaries before using later data for retraining, and keep a holdout test set out of training.

## Cost and operational limits

Glue charges accrue while the Spark job runs. The completion-marker S3 event starts Glue automatically, so upload all event files first and the marker last. Start with one small historical batch and inspect its logs, audit rows, and S3 outputs before processing other batches. A successful manifest automatically starts the model-training Lambda; model-registration details and approval status are in the [model-training runbook](model-training-lambda.md).

# Event-triggered model training

This runbook describes the SentinelPay model-training Lambda. It trains a versioned Logistic Regression artifact from a successful Glue export. It does not deploy a model to a payment-serving endpoint or replace the currently used model automatically.

## Trigger and data flow

1. Upload all raw event families for a batch. The project landing command writes `raw/metadata/ingest_date=<date>/batch_id=<batch>/batch_complete.json` last.
2. S3 invokes `sentinelpay-glue-starter-dev` for that ready marker. The starter validates the marker, starts `sentinelpay-batch-etl-dev` with its date and batch ID, and avoids starting a second active or successful run for the same batch.
3. Glue finishes the Gold refresh and writes the train, validation, and test Parquet folders to `ml/training_exports/glue/export_id=<glue-run-id>/`.
4. Glue writes its run manifest last under `ops/glue_batch_runs/.../manifest.json`. S3 invokes the model-training Lambda for this completion manifest. This single completion event acts as the barrier for all three split exports; split-object events could arrive before all folders are complete.
5. The training Lambda reads the manifest and skips unsuccessful jobs, non-synthetic data, or exports below the configured row minimums.
6. It downloads Parquet files from all three S3 split prefixes. It verifies the 30-day minimum label delay, row counts from the manifest, minimum fraud examples, and no payment-ID overlap.
7. It trains on TRAIN, selects the probability threshold using VALIDATION, and reports final metrics using TEST.
8. It writes versioned artifacts to `ml/models/export_id=<glue-run-id>/`. The model file is written first; `metrics.json` is written last and serves as the idempotency marker for duplicate S3 notifications.

Run `scripts/land_complete_batch.py` to upload all event families and automatically publish the completion marker. For manual S3 console uploads, upload all event files first, then upload a matching `batch_complete.json` marker to the path above. The marker is the explicit signal that the batch is complete.

Default maturity gates are 500 TRAIN rows, 100 VALIDATION rows, 100 TEST rows, at least 10 fraud labels in every split, and a 30-day label delay. Terraform variables can tune these thresholds. The event triggers only after the Glue job has exported all current mature Gold rows; the gate prevents training on small or class-incomplete snapshots.

## Deployment

The function is packaged as a Lambda container image because the existing trainer depends on scikit-learn and PyArrow. Build and push an immutable image tag to the ECR repository created by Terraform, then apply the Lambda resources:

```sh
python3 scripts/package_glue_job_starter.py
terraform -chdir=infra/terraform fmt
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -target=aws_ecr_repository.model_training
terraform -chdir=infra/terraform apply -target=aws_ecr_repository.model_training

SENTINELPAY_REGION=ap-southeast-2 SENTINELPAY_MODEL_IMAGE_TAG=v3 scripts/deploy_model_training_image.sh

terraform -chdir=infra/terraform plan -target=aws_lambda_function.glue_starter -target=aws_lambda_function.model_training -target=aws_s3_bucket_notification.model_training
terraform -chdir=infra/terraform apply -target=aws_lambda_function.glue_starter -target=aws_lambda_function.model_training -target=aws_s3_bucket_notification.model_training
```

The Glue starter uses a small Python Lambda and can only read batch completion markers and start the configured Glue job. The model-training function uses 3,008 MB memory, 4 GB `/tmp`, and a 15-minute timeout. Its IAM access is scoped to Glue manifests, the three Glue export prefixes, and versioned model outputs in the project bucket. S3 conditional lock objects prevent concurrent duplicate training of the same export; leases expire after 20 minutes if an invocation is terminated. Both function log groups expire after 14 days.

## Outputs and operations

- Model: `s3://<bucket>/ml/models/export_id=<glue-run-id>/logistic_regression_baseline.joblib`
- Metrics: `s3://<bucket>/ml/models/export_id=<glue-run-id>/metrics.json`
- Logs: `/aws/lambda/sentinelpay-model-trainer-dev`

Failed invocations are retried twice. A duplicate event for an export with a completed `metrics.json` is skipped. A run without enough rows or fraud examples is logged as skipped and does not write a model artifact. Each export ID gets its own immutable S3 prefix; model promotion remains a separate approval step.

The Lambda is appropriate for the current small synthetic portfolio dataset. If export size or training time approaches the configured Lambda limits, move the training compute to SageMaker or another batch service and keep the completion trigger as the orchestrator.

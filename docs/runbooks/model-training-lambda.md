# Event-triggered model training and registration

This runbook describes the SentinelPay model-training Lambda. It trains a versioned Logistic Regression artifact from a successful Glue export. Model package registration is separate from endpoint deployment: approved packages must be deployed manually, and a new package never replaces the endpoint automatically.

## Trigger and data flow

1. Upload all raw event families for a batch. The project landing command writes `raw/metadata/ingest_date=<date>/batch_id=<batch>/batch_complete.json` last.
2. S3 invokes `sentinelpay-glue-starter-dev` for that ready marker. The starter validates the marker, starts `sentinelpay-batch-etl-dev` with its date and batch ID, and avoids starting a second active or successful run for the same batch.
3. Glue finishes the Gold refresh and writes the train, validation, and test Parquet folders to `ml/training_exports/glue/export_id=<glue-run-id>/`.
4. Glue writes its run manifest last under `ops/glue_batch_runs/.../manifest.json`. S3 invokes the model-training Lambda for this completion manifest. This single completion event acts as the barrier for all three split exports; split-object events could arrive before all folders are complete.
5. The training Lambda reads the manifest and skips unsuccessful jobs, non-synthetic data, or exports below the configured row minimums.
6. It downloads Parquet files from all three S3 split prefixes. It verifies the 30-day minimum label delay, row counts from the manifest, minimum fraud examples, and no payment-ID overlap.
7. It trains on TRAIN, selects the probability threshold using VALIDATION, and reports final metrics using TEST.
8. It writes versioned artifacts to `ml/models/export_id=<glue-run-id>/`. The model file is written first; `metrics.json` is written last and serves as the idempotency marker for duplicate S3 notifications.
9. The training Lambda starts the separate `sentinelpay-model-registry-dev` SageMaker Pipeline with the model, metrics, and Glue export ID. The pipeline invokes a registry gate that reads the held-out TEST ROC-AUC and compares it with the best completed package in the `sentinelpay-fraud-models-dev` Model Package Group.
10. A strictly higher TEST ROC-AUC is packaged with an inference package and registered as a new model package version with `PendingManualApproval`. The package points `SAGEMAKER_SUBMIT_DIRECTORY` at `/opt/ml/model/code`. Equal or lower scores are not registered; repeated events for the same export do not create a duplicate version. The pipeline does not create or update an endpoint.

Run `scripts/land_complete_batch.py` to upload all event families and automatically publish the completion marker. For manual S3 console uploads, upload all event files first, then upload a matching `batch_complete.json` marker to the path above. The marker is the explicit signal that the batch is complete.

Default maturity gates are 500 TRAIN rows, 100 VALIDATION rows, 100 TEST rows, at least 10 fraud labels in every split, and a 30-day label delay. Terraform variables can tune these thresholds. The event triggers only after the Glue job has exported all current mature Gold rows; the gate prevents training on small or class-incomplete snapshots.

## Deployment

The function is packaged as a Lambda container image because the existing trainer depends on scikit-learn and PyArrow. The separate registry gate is a small Python Lambda, orchestrated by SageMaker Pipelines. Build and push an immutable image tag to the ECR repository created by Terraform, then apply the Lambda resources:

```sh
python3 scripts/package_glue_job_starter.py
python3 scripts/package_model_registry_lambda.py
terraform -chdir=infra/terraform fmt
terraform -chdir=infra/terraform init

SENTINELPAY_REGION=ap-southeast-2 SENTINELPAY_MODEL_IMAGE_TAG=v4 scripts/deploy_model_training_image.sh

terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -out=/tmp/sentinelpay-model-flow.tfplan
terraform -chdir=infra/terraform apply /tmp/sentinelpay-model-flow.tfplan
```

The Glue starter uses a small Python Lambda and can only read batch completion markers and start the configured Glue job. The model-training function uses 3,008 MB memory, 4 GB `/tmp`, and a 15-minute timeout. Its IAM access is scoped to Glue manifests, the three Glue export prefixes, versioned model outputs, and starting this registry pipeline. The registry gate has S3 access only to the model and candidate artifact prefixes. SageMaker package list/create actions use `Resource: "*"` because SageMaker authorizes these APIs against package ARNs (including a temporary `new` ARN); the gate's code fixes the target to `sentinelpay-fraud-models-dev` and does not accept a package group from pipeline input. S3 conditional lock objects prevent concurrent duplicate training of the same export; leases expire after 20 minutes if an invocation is terminated. Function log groups expire after 14 days.

## Outputs and operations

- Model: `s3://<bucket>/ml/models/export_id=<glue-run-id>/logistic_regression_baseline.joblib`
- Metrics: `s3://<bucket>/ml/models/export_id=<glue-run-id>/metrics.json`
- Logs: `/aws/lambda/sentinelpay-model-trainer-dev`
- SageMaker Pipeline: `sentinelpay-model-registry-dev`
- Model Package Group: `sentinelpay-fraud-models-dev`
- Candidate package artifacts: `s3://<bucket>/ml/models/registry/candidates/export_id=<glue-run-id>/model.tar.gz`
- Current working serving package: `4` (`arn:aws:sagemaker:ap-southeast-2:908768512617:model-package/sentinelpay-fraud-models-dev/4`)
- TEST ROC-AUC: `0.8570074074`; approval status: `Approved`. Version 4 uses the existing trained weights and corrects the inference package path; it is not a newly trained model.

Failed invocations are retried twice. A duplicate event for an export with a completed `metrics.json` skips retraining and safely re-enters the registration pipeline. A run without enough rows or fraud examples is logged as skipped and does not write a model artifact. Each export ID gets its own immutable S3 prefix; model package promotion remains a separate manual approval step in SageMaker Model Registry.

To review packages, open **SageMaker AI → Model Registry → `sentinelpay-fraud-models-dev`** in `ap-southeast-2`. The registry pipeline registers improved candidates as `PendingManualApproval`; an owner reviews and approves the candidate. Approval alone does not deploy it.

## Demo endpoint

Package version 4 is manually deployed to `Endpoint-20261107-v4` in `ap-southeast-2`, using one `ml.c6i.large` instance. The earlier endpoint attempts `Endpoint-20261106-110549` and `Endpoint-20261107-v3` used incorrect inference code paths; version 2 and 3 are rejected in Model Registry. Version 4 passes the container health check and a test invocation.

The endpoint accepts one or more feature rows in this order: `amount`, `device_first_seen_days`, `transaction_count_1h`, `amount_sum_1h`, `distinct_merchant_count_1h`, `new_device_count_1h`, `currency`, `channel`, `country_code`.

```json
{"instances":[[125.50,14,3,280.0,2,1,"AUD","CARD_NOT_PRESENT","AU"]]}
```

The tested response was fraud probability `0.548069`, prediction `0`, with threshold `0.648958`. This is a synthetic demo request. The real-time endpoint incurs instance charges while it is running; delete it when the demo is finished. For example:

```sh
aws sagemaker delete-endpoint --endpoint-name Endpoint-20261107-v4 --region ap-southeast-2
```

The Lambda is appropriate for the current small synthetic portfolio dataset. If export size or training time approaches the configured Lambda limits, move the training compute to SageMaker or another batch service and keep the completion trigger as the orchestrator.

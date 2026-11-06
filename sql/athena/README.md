# Athena query set

Run the files one at a time in this order in the Athena workgroup and database `sentinelpay`:

1. `00_create_*_bronze.sql` — create the four JSON external tables.
2. `00_repair_*_bronze.sql` — discover the Hive partitions under the S3 raw prefixes.
3. `01_create_*_iceberg.sql` — create the four Silver Iceberg tables.
4. `01_bronze_batch_reconciliation.sql` — check raw record counts and duplicate delivery counts.
5. `02_merge_*_to_silver.sql` — deduplicate and merge valid events into Silver. Historical validation/test identifiers are namespaced by batch to prevent synthetic ID collisions.
6. `02_silver_uniqueness.sql` — check Silver event-key uniqueness.
7. `04_gold_label_feature_coverage.sql` — check matured labels and point-in-time features.
8. `03_create_*_gold.sql`, `03_merge_training_examples_gold.sql`, and `03_merge_fraud_daily_metrics_gold.sql` — create and populate Gold training examples and daily metrics.
9. `03_gold_*.sql` — check split sizes, date coverage, and split overlap.
10. `04_create_pipeline_audit.sql`, `04_merge_pipeline_audit.sql` — create and populate batch reconciliation history.
11. `06_pipeline_audit.sql` and `07_pipeline_audit_failures.sql` — inspect audit results.
12. `05_streaming_*.sql` — verify the 21-event Firehose smoke batch, Silver matches, and streaming audit row. Update the date if using another ingestion day.
13. `08_export_training_examples.sql` — optional Parquet export for local baseline training.

The SQL here combines the statements visible in Athena history with the project contracts and the resulting schema/counts to provide a complete ordered set. Check the S3 bucket and database names before running it in another account. The `CREATE TABLE IF NOT EXISTS` statements do not replace or alter existing tables; for a rebuild, use a clean database or explicitly migrate the existing tables after checking their catalog definitions.

The export query writes to a new prefix. Change `export_id` for every new export because Athena UNLOAD requires a destination without existing objects. The query keeps `dataset_split` as the final selected column for partitioned output.

## Automated batch processing

The Glue implementation is in `src/glue/sentinelpay_batch_job.py`, with its job and scoped execution role in `infra/terraform/glue.tf` and `infra/terraform/glue_iam.tf`. An S3 batch-complete marker starts it; it reads the exact raw batch prefixes so it can preserve malformed input for quarantine, then merges validated records into the existing Iceberg tables. The successful Glue manifest triggers the training Lambda, which starts SageMaker Pipelines for model comparison and registration. The Bronze Athena tables remain available for querying and reconciliation. See [the Glue batch runbook](../../docs/runbooks/glue-batch-etl.md) and [the model-training and registration runbook](../../docs/runbooks/model-training-lambda.md) before deploying or starting the job.

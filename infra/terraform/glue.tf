locals {
  glue_batch_script_key = "artifacts/glue/sentinelpay_batch_job.py"
  glue_iceberg_spark_conf = join(" ", [
    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "--conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog",
    "--conf spark.sql.catalog.glue_catalog.warehouse=s3://${aws_s3_bucket.raw.bucket}/",
    "--conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog",
    "--conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO"
  ])
}

resource "aws_s3_object" "glue_batch_script" {
  bucket       = aws_s3_bucket.raw.id
  key          = local.glue_batch_script_key
  source       = "${path.module}/../../src/glue/sentinelpay_batch_job.py"
  source_hash  = filemd5("${path.module}/../../src/glue/sentinelpay_batch_job.py")
  content_type = "text/x-python"
}

resource "aws_glue_job" "batch_processing" {
  name              = var.glue_job_name
  role_arn          = aws_iam_role.glue_batch.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 45
  max_retries       = 0

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.raw.bucket}/${local.glue_batch_script_key}"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"                 = "iceberg"
    "--enable-glue-datacatalog"          = ""
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--TempDir"                          = "s3://${aws_s3_bucket.raw.bucket}/tmp/glue/"
    "--conf"                             = local.glue_iceberg_spark_conf
    "--bucket"                           = aws_s3_bucket.raw.bucket
    "--database"                         = var.glue_database
    "--namespace_batches"                = "*"
    "--quarantine_prefix"                = "quarantine/records"
    "--export_prefix"                    = "ml/training_exports/glue"
    "--train_cutoff"                     = "2026-06-01"
    "--validation_cutoff"                = "2026-09-01"
    "--max_invalid_fraction"             = "0.05"
  }

  depends_on = [
    aws_s3_object.glue_batch_script,
    aws_iam_role_policy.glue_batch_access
  ]
}

data "aws_caller_identity" "glue" {}

data "aws_kms_alias" "glue_s3" {
  name = "alias/aws/s3"
}

data "aws_iam_policy_document" "glue_batch_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_batch" {
  name               = "${var.project_name}-glue-batch-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.glue_batch_trust.json
}

data "aws_iam_policy_document" "glue_batch_access" {
  statement {
    sid    = "ReadAndWriteProjectBucket"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:ListBucketMultipartUploads"
    ]
    resources = [aws_s3_bucket.raw.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "raw/*", "silver/*", "gold/*", "quarantine/*", "ops/*",
        "tmp/glue/*", "ml/training_exports/glue/*", "artifacts/glue/*"
      ]
    }
  }

  statement {
    sid     = "ReadSourceAndLakehouseData"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.raw.arn}/raw/*",
      "${aws_s3_bucket.raw.arn}/silver/*",
      "${aws_s3_bucket.raw.arn}/gold/*",
      "${aws_s3_bucket.raw.arn}/artifacts/glue/*"
    ]
  }

  statement {
    sid    = "WriteProjectOutputs"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
      "s3:PutObject"
    ]
    resources = [
      "${aws_s3_bucket.raw.arn}/silver/*",
      "${aws_s3_bucket.raw.arn}/gold/*",
      "${aws_s3_bucket.raw.arn}/quarantine/*",
      "${aws_s3_bucket.raw.arn}/ops/*",
      "${aws_s3_bucket.raw.arn}/tmp/glue/*",
      "${aws_s3_bucket.raw.arn}/ml/training_exports/glue/*"
    ]
  }

  statement {
    sid     = "RemoveRewrittenOutputObjects"
    effect  = "Allow"
    actions = ["s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.raw.arn}/silver/*",
      "${aws_s3_bucket.raw.arn}/gold/*",
      "${aws_s3_bucket.raw.arn}/ops/*",
      "${aws_s3_bucket.raw.arn}/tmp/glue/*",
      "${aws_s3_bucket.raw.arn}/ml/training_exports/glue/*"
    ]
  }

  statement {
    sid    = "UseBucketEncryptionKey"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:ReEncryptFrom",
      "kms:ReEncryptTo"
    ]
    resources = [data.aws_kms_alias.glue_s3.target_key_arn]
  }

  statement {
    sid    = "ReadAndCommitGlueCatalogTables"
    effect = "Allow"
    actions = [
      "glue:BatchGetPartition",
      "glue:GetCatalog",
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdateTable"
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.glue.account_id}:catalog",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.glue.account_id}:database/${var.glue_database}",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.glue.account_id}:table/${var.glue_database}/*"
    ]
  }

  statement {
    sid    = "WriteGlueJobLogsAndMetrics"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "glue_batch_access" {
  name   = "${var.project_name}-glue-batch-access-${var.environment}"
  role   = aws_iam_role.glue_batch.id
  policy = data.aws_iam_policy_document.glue_batch_access.json
}

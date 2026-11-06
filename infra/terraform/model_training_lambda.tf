locals {
  model_training_function_name   = "${var.project_name}-model-trainer-${var.environment}"
  glue_starter_function_name     = "${var.project_name}-glue-starter-${var.environment}"
  model_training_image_uri       = "${aws_ecr_repository.model_training.repository_url}:${var.model_training_image_tag}"
  model_training_manifest_prefix = "ops/glue_batch_runs/"
  model_training_export_prefix   = "ml/training_exports/glue/"
  model_training_output_prefix   = "ml/models/"
  raw_batch_completion_prefix    = "raw/metadata/"
}

data "aws_iam_policy_document" "glue_starter_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_starter" {
  name               = "${var.project_name}-glue-starter-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.glue_starter_trust.json
}

resource "aws_iam_role_policy_attachment" "glue_starter_logs" {
  role       = aws_iam_role.glue_starter.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "glue_starter_access" {
  statement {
    sid       = "ReadBatchCompletionManifest"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.raw.arn}/${local.raw_batch_completion_prefix}*"]
  }

  statement {
    sid       = "StartSentinelPayBatchJob"
    effect    = "Allow"
    actions   = ["glue:StartJobRun"]
    resources = ["arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:job/${var.glue_job_name}"]
  }

  statement {
    sid       = "CheckExistingSentinelPayRuns"
    effect    = "Allow"
    actions   = ["glue:GetJobRuns"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "glue_starter_access" {
  name   = "${var.project_name}-glue-starter-access-${var.environment}"
  role   = aws_iam_role.glue_starter.id
  policy = data.aws_iam_policy_document.glue_starter_access.json
}

resource "aws_cloudwatch_log_group" "glue_starter" {
  name              = "/aws/lambda/${local.glue_starter_function_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "glue_starter" {
  function_name    = local.glue_starter_function_name
  role             = aws_iam_role.glue_starter.arn
  filename         = "${path.module}/glue_job_starter.zip"
  source_code_hash = filebase64sha256("${path.module}/glue_job_starter.zip")
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      BUCKET        = aws_s3_bucket.raw.bucket
      GLUE_JOB_NAME = var.glue_job_name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.glue_starter_logs,
    aws_iam_role_policy.glue_starter_access,
    aws_cloudwatch_log_group.glue_starter
  ]
}

resource "aws_lambda_function_event_invoke_config" "glue_starter" {
  function_name                = aws_lambda_function.glue_starter.function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 2
}

resource "aws_lambda_permission" "glue_starter_from_s3" {
  statement_id   = "AllowInvokeFromRawBatchCompletion"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.glue_starter.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.raw.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_ecr_repository" "model_training" {
  name                 = "${var.project_name}-model-training-${var.environment}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "model_training" {
  repository = aws_ecr_repository.model_training.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the five most recent model trainer images"
      selection = {
        tagStatus     = "tagged"
        tagPrefixList = ["v"]
        countType     = "imageCountMoreThan"
        countNumber   = 5
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecr_repository_policy" "model_training" {
  repository = aws_ecr_repository.model_training.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LambdaImageReadForModelTrainer"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      Condition = {
        StringLike = {
          "aws:SourceArn" = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.model_training_function_name}"
        }
      }
    }]
  })
}

data "aws_iam_policy_document" "model_training_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "model_training" {
  name               = "${var.project_name}-model-training-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.model_training_trust.json
}

resource "aws_iam_role_policy_attachment" "model_training_logs" {
  role       = aws_iam_role.model_training.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "model_training_access" {
  statement {
    sid       = "ListTrainingInputsAndOutputs"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.raw.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.model_training_manifest_prefix}*",
        "${local.model_training_export_prefix}*",
        "${local.model_training_output_prefix}*"
      ]
    }
  }

  statement {
    sid     = "ReadGlueManifestsAndParquetSplits"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.raw.arn}/${local.model_training_manifest_prefix}*",
      "${aws_s3_bucket.raw.arn}/${local.model_training_export_prefix}*",
      "${aws_s3_bucket.raw.arn}/${local.model_training_output_prefix}locks/*"
    ]
  }

  statement {
    sid       = "WriteVersionedModelArtifacts"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/${local.model_training_output_prefix}*"]
  }

  statement {
    sid       = "ReleaseExpiredTrainingLocks"
    effect    = "Allow"
    actions   = ["s3:DeleteObject"]
    resources = ["${aws_s3_bucket.raw.arn}/${local.model_training_output_prefix}locks/*"]
  }

  statement {
    sid    = "UseProjectS3EncryptionKey"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey"
    ]
    resources = [data.aws_kms_alias.glue_s3.target_key_arn]
  }
}

resource "aws_iam_role_policy" "model_training_access" {
  name   = "${var.project_name}-model-training-access-${var.environment}"
  role   = aws_iam_role.model_training.id
  policy = data.aws_iam_policy_document.model_training_access.json
}

resource "aws_cloudwatch_log_group" "model_training" {
  name              = "/aws/lambda/${local.model_training_function_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "model_training" {
  function_name = local.model_training_function_name
  role          = aws_iam_role.model_training.arn
  package_type  = "Image"
  image_uri     = local.model_training_image_uri
  architectures = ["x86_64"]
  timeout       = 900
  memory_size   = 3008

  ephemeral_storage {
    size = 4096
  }

  environment {
    variables = {
      MANIFEST_PREFIX          = local.model_training_manifest_prefix
      EXPORT_PREFIX            = local.model_training_export_prefix
      MODEL_PREFIX             = local.model_training_output_prefix
      MIN_TRAIN_ROWS           = tostring(var.model_training_min_train_rows)
      MIN_VALIDATION_ROWS      = tostring(var.model_training_min_validation_rows)
      MIN_TEST_ROWS            = tostring(var.model_training_min_test_rows)
      MIN_FRAUD_ROWS_PER_SPLIT = tostring(var.model_training_min_fraud_rows_per_split)
      MIN_LABEL_DELAY_DAYS     = tostring(var.model_training_min_label_delay_days)
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.model_training_logs,
    aws_iam_role_policy.model_training_access,
    aws_cloudwatch_log_group.model_training,
    aws_ecr_repository_policy.model_training
  ]
}

resource "aws_lambda_function_event_invoke_config" "model_training" {
  function_name                = aws_lambda_function.model_training.function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 2
}

resource "aws_lambda_permission" "model_training_from_s3" {
  statement_id   = "AllowInvokeFromGlueRunManifests"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.model_training.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.raw.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "model_training" {
  bucket = aws_s3_bucket.raw.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.glue_starter.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.raw_batch_completion_prefix
    filter_suffix       = "batch_complete.json"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.model_training.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.model_training_manifest_prefix
    filter_suffix       = "manifest.json"
  }

  depends_on = [
    aws_lambda_permission.model_training_from_s3,
    aws_lambda_permission.glue_starter_from_s3
  ]
}

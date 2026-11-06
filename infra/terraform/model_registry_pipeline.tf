locals {
  model_registry_function_name   = "${var.project_name}-model-registry-gate-${var.environment}"
  model_registry_group_name      = "${var.project_name}-fraud-models-${var.environment}"
  model_registry_pipeline_name   = "${var.project_name}-model-registry-${var.environment}"
  model_registry_inference_image = "783357654285.dkr.ecr.${var.aws_region}.amazonaws.com/sagemaker-scikit-learn:1.9-0"
}

resource "aws_sagemaker_model_package_group" "fraud" {
  model_package_group_name        = local.model_registry_group_name
  model_package_group_description = "Versioned SentinelPay fraud models evaluated by the separate SageMaker registry pipeline"
}

data "aws_iam_policy_document" "model_registry_lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "model_registry_lambda" {
  name               = "${var.project_name}-model-registry-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.model_registry_lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "model_registry_lambda_logs" {
  role       = aws_iam_role.model_registry_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "model_registry_lambda_access" {
  statement {
    sid     = "ReadTrainedModelsAndMetrics"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.raw.arn}/${local.model_training_output_prefix}export_id=*/*",
      "${aws_s3_bucket.raw.arn}/${local.model_training_output_prefix}registry/candidates/*"
    ]
  }

  statement {
    sid       = "WriteRegistryCandidateArtifacts"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/${local.model_training_output_prefix}registry/candidates/*"]
  }

  statement {
    # SageMaker authorizes ListModelPackages against package resources and
    # CreateModelPackage against a temporary "new" package ARN; these APIs do
    # not support reliably scoping the request to the group ARN. The Lambda
    # keeps the target group fixed in MODEL_PACKAGE_GROUP and never accepts it
    # from pipeline input.
    sid       = "ListModelPackagesForRegistryComparison"
    effect    = "Allow"
    actions   = ["sagemaker:ListModelPackages"]
    resources = ["*"]
  }

  statement {
    sid       = "CreateModelPackageForConfiguredRegistryGroup"
    effect    = "Allow"
    actions   = ["sagemaker:CreateModelPackage"]
    resources = ["*"]
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

resource "aws_iam_role_policy" "model_registry_lambda_access" {
  name   = "${var.project_name}-model-registry-access-${var.environment}"
  role   = aws_iam_role.model_registry_lambda.id
  policy = data.aws_iam_policy_document.model_registry_lambda_access.json
}

resource "aws_cloudwatch_log_group" "model_registry_lambda" {
  name              = "/aws/lambda/${local.model_registry_function_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "model_registry" {
  function_name    = local.model_registry_function_name
  role             = aws_iam_role.model_registry_lambda.arn
  filename         = "${path.module}/model_registry_lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/model_registry_lambda.zip")
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      MODEL_PACKAGE_GROUP = aws_sagemaker_model_package_group.fraud.model_package_group_name
      INFERENCE_IMAGE     = local.model_registry_inference_image
      MODEL_PREFIX        = local.model_training_output_prefix
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.model_registry_lambda_logs,
    aws_iam_role_policy.model_registry_lambda_access,
    aws_cloudwatch_log_group.model_registry_lambda
  ]
}

data "aws_iam_policy_document" "model_registry_pipeline_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:pipeline/${local.model_registry_pipeline_name}/*"]
    }
  }
}

resource "aws_iam_role" "model_registry_pipeline" {
  name               = "${var.project_name}-registry-pipeline-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.model_registry_pipeline_trust.json
}

data "aws_iam_policy_document" "model_registry_pipeline_access" {
  statement {
    sid       = "InvokeRegistryGate"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.model_registry.arn]
  }
}

resource "aws_iam_role_policy" "model_registry_pipeline_access" {
  name   = "${var.project_name}-registry-pipeline-access-${var.environment}"
  role   = aws_iam_role.model_registry_pipeline.id
  policy = data.aws_iam_policy_document.model_registry_pipeline_access.json
}

resource "aws_sagemaker_pipeline" "model_registry" {
  pipeline_name         = local.model_registry_pipeline_name
  pipeline_display_name = "SentinelPay-Improved-Model-Registration"
  pipeline_description  = "Compares Glue-trained candidate test ROC-AUC with the best registered version and registers only improvements for manual approval."
  role_arn              = aws_iam_role.model_registry_pipeline.arn
  pipeline_definition = jsonencode({
    Version = "2020-12-01"
    Parameters = [
      { Name = "ModelUri", Type = "String" },
      { Name = "MetricsUri", Type = "String" },
      { Name = "ExportId", Type = "String" }
    ]
    Steps = [{
      Name = "CompareAndRegisterImprovedModel"
      Type = "Lambda"
      Arguments = {
        model_uri   = { "Get" = "Parameters.ModelUri" }
        metrics_uri = { "Get" = "Parameters.MetricsUri" }
        export_id   = { "Get" = "Parameters.ExportId" }
      }
      FunctionArn = aws_lambda_function.model_registry.arn
      OutputParameters = [
        { OutputName = "status", OutputType = "String" },
        { OutputName = "model_package_arn", OutputType = "String" },
        { OutputName = "test_roc_auc", OutputType = "String" }
      ]
    }]
  })

  depends_on = [
    aws_iam_role_policy.model_registry_pipeline_access,
    aws_lambda_function.model_registry
  ]
}

data "aws_iam_policy_document" "model_training_pipeline_access" {
  statement {
    sid       = "StartModelRegistryPipeline"
    effect    = "Allow"
    actions   = ["sagemaker:StartPipelineExecution"]
    resources = [aws_sagemaker_pipeline.model_registry.arn]
  }
}

resource "aws_iam_role_policy" "model_training_pipeline_access" {
  name   = "${var.project_name}-model-training-pipeline-${var.environment}"
  role   = aws_iam_role.model_training.id
  policy = data.aws_iam_policy_document.model_training_pipeline_access.json
}

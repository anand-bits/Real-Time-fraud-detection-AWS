data "aws_kms_alias" "kinesis" {
  name = "alias/aws/kinesis"
}

data "aws_kms_alias" "s3" {
  name = "alias/aws/s3"
}

locals {
  firehose_delivery_name = "${var.project_name}-raw-delivery-${var.environment}"
}

resource "aws_iam_role" "firehose_delivery" {
  name = "${var.project_name}-firehose-delivery-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "firehose.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:firehose:${var.aws_region}:${data.aws_caller_identity.current.account_id}:deliverystream/${local.firehose_delivery_name}"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "firehose_delivery" {
  name = "${var.project_name}-firehose-delivery-${var.environment}"
  role = aws_iam_role.firehose_delivery.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadPaymentStream"
        Effect = "Allow"
        Action = [
          "kinesis:DescribeStream",
          "kinesis:GetShardIterator",
          "kinesis:GetRecords",
          "kinesis:ListShards"
        ]
        Resource = aws_kinesis_stream.payments.arn
      },
      {
        Sid      = "DecryptPaymentStreamRecords"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = data.aws_kms_alias.kinesis.target_key_arn
      },
      {
        Sid    = "ListRawBucket"
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads"
        ]
        Resource = aws_s3_bucket.raw.arn
      },
      {
        Sid    = "WriteRawAndErrorObjects"
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          "${aws_s3_bucket.raw.arn}/raw/payments/*",
          "${aws_s3_bucket.raw.arn}/errors/*"
        ]
      },
      {
        Sid    = "UseBucketEncryptionKey"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = data.aws_kms_alias.s3.target_key_arn
        Condition = {
          StringEquals = {
            "kms:ViaService"                   = "s3.${var.aws_region}.amazonaws.com"
            "kms:EncryptionContext:aws:s3:arn" = aws_s3_bucket.raw.arn
          }
        }
      }
    ]
  })
}
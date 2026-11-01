resource "aws_kinesis_firehose_delivery_stream" "payments_to_s3" {
  name        = local.firehose_delivery_name
  destination = "extended_s3"

  kinesis_source_configuration {
    kinesis_stream_arn = aws_kinesis_stream.payments.arn
    role_arn           = aws_iam_role.firehose_delivery.arn
  }

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose_delivery.arn
    bucket_arn = aws_s3_bucket.raw.arn

    prefix              = "raw/payments/"
    error_output_prefix = "errors/!{firehose:error-output-type}/!{timestamp:yyyy/MM/dd/HH}/"

    buffering_size     = 1
    buffering_interval = 60
    compression_format = "GZIP"

    processing_configuration {
      enabled = true

      processors {
        type = "AppendDelimiterToRecord"
      }
    }
  }
}
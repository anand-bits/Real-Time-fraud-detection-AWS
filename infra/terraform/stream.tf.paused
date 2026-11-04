resource "aws_kinesis_stream" "payments" {
  name             = "${var.project_name}-payments-${var.environment}"
  retention_period = 24
  encryption_type  = "KMS"
  kms_key_id       = "alias/aws/kinesis"

  stream_mode_details {
    stream_mode = "ON_DEMAND"
  }
}
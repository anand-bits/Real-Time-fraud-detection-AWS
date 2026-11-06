variable "aws_region" {
  description = "AWS Region for the SentinelPay learning project"
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Short project name used to label resources"
  type        = string
  default     = "sentinelpay"
}

variable "environment" {
  description = "Environment name for this deployment"
  type        = string
  default     = "dev"
}

variable "glue_database" {
  description = "Existing Glue Data Catalog database containing the SentinelPay tables"
  type        = string
  default     = "sentinelpay"
}

variable "glue_job_name" {
  description = "Name of the single-batch Glue Spark ETL job"
  type        = string
  default     = "sentinelpay-batch-etl-dev"
}

variable "model_training_image_tag" {
  description = "Immutable ECR tag for the model-training Lambda container image"
  type        = string
  default     = "v3"
}

variable "model_training_min_train_rows" {
  description = "Minimum mature rows required in the TRAIN split before retraining"
  type        = number
  default     = 500
}

variable "model_training_min_validation_rows" {
  description = "Minimum mature rows required in the VALIDATION split before retraining"
  type        = number
  default     = 100
}

variable "model_training_min_test_rows" {
  description = "Minimum mature rows required in the TEST split before retraining"
  type        = number
  default     = 100
}

variable "model_training_min_fraud_rows_per_split" {
  description = "Minimum positive fraud labels required in every split before retraining"
  type        = number
  default     = 10
}

variable "model_training_min_label_delay_days" {
  description = "Minimum days between payment event time and observed label"
  type        = number
  default     = 30
}

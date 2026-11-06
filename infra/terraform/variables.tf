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

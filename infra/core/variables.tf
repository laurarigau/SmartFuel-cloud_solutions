variable "region" {
  description = "AWS region (the shared account only allows eu-north-1)"
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Prefix for every resource name"
  type        = string
  default     = "smartfuel"
}

variable "suffix" {
  description = "Unique suffix for S3 bucket names. scripts/deploy.sh sets it to the AWS account id."
  type        = string
}

variable "raw_to_glacier_days" {
  description = "Days before raw/ objects move to Glacier"
  type        = number
  default     = 30
}

variable "admin_emails" {
  description = "Emails subscribed to the admin-alerts SNS topic (each must confirm the subscription)"
  type        = list(string)
  default     = []
}

variable "enable_messaging" {
  description = "Enable SNS and SQS resources when permitted"
  type        = bool
  default     = true
}

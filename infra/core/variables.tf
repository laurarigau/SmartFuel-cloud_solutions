variable "region" {
  description = "AWS region of the sandbox"
  type        = string
  default     = "us-east-1"
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

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
  description = "Unique suffix for globally-named resources (S3). Use the shared sandbox's value."
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

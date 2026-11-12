variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "smartfuel"
}

variable "state_bucket" {
  description = "S3 bucket holding the Terraform state (to read the core stack outputs)"
  type        = string
}

variable "ingest_region" {
  description = "Region where the ingest Lambda runs (must reach the Ministry API)"
  type        = string
  default     = "us-east-1"
}

variable "ingest_schedule" {
  description = "When to download prices (Madrid time): 01:00, 07:00, 13:00 and 19:00"
  type        = string
  default     = "cron(0 1,7,13,19 * * ? *)"
}

variable "region" {
  type    = string
  default = "eu-north-1"
}

variable "project" {
  type    = string
  default = "smartfuel"
}

variable "state_bucket" {
  description = "S3 bucket holding the Terraform state (to read the core stack outputs)"
  type        = string
}

variable "pandas_layer_arn" {
  description = "AWS SDK for pandas layer ARN (Python 3.12, x86_64). Empty = latest, read from AWS public SSM parameters."
  type        = string
  default     = ""
}

variable "min_stations" {
  description = "validate: minimum number of stations for a raw file to be valid"
  type        = number
  default     = 10000
}

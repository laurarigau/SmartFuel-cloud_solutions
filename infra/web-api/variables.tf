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

variable "suffix" {
  description = "Unique suffix (the AWS account id, set by deploy.sh). Used in the Cognito login domain"
  type        = string
}

variable "web_urls" {
  description = "Where the web app runs: Cognito sends the user back here after log-in / log-out"
  type        = list(string)
  default     = ["http://localhost:8000/"]
}

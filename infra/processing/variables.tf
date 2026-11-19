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

variable "predict_lambda_arn" {
  description = "Optional Phase C ML Lambda ARN. Empty = use_ml_predict decides."
  type        = string
  default     = ""
}

variable "use_ml_predict" {
  description = "Predict with the Phase C model (Lambda <project>-predict-ml) instead of the provisional predict Lambda"
  type        = bool
  default     = true
}
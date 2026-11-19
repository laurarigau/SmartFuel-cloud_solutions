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

variable "alarm_emails" {
  description = "Who receives the alarm emails (each must confirm the subscription)"
  type        = list(string)
  default = [
    "marta.palet@alumni.esade.edu",
    "marc.farras@alumni.esade.edu",
    "carla.escassi@alumni.esade.edu",
    "laura.rigau@alumni.esade.edu",
  ]
}

variable "lambda_functions" {
  description = "Lambdas whose errors raise an alarm (a missing one just never fires)"
  type        = list(string)
  default = [
    "ingest",
    "validate",
    "clean",
    "save-changes",
    "predict",
    "predict-ml",
    "check-alerts",
    "send-email",
    "train",
    "evaluate",
    "api",
  ]
}

variable "state_machines" {
  description = "Step Functions workflows whose failed executions raise an alarm"
  type        = list(string)
  default     = ["processing", "ml-retraining"]
}

variable "ingest_every_hours" {
  description = "The ingestion runs every 6 hours; the alarm fires after 2 periods without runs"
  type        = number
  default     = 6
}

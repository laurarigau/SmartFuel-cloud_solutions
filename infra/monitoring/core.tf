# Outputs of the shared stack (bucket, tables, topics, DLQ).
data "terraform_remote_state" "core" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "core/terraform.tfstate"
    region = var.region
  }
}

locals {
  core = data.terraform_remote_state.core.outputs
}

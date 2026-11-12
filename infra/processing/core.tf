# Outputs of the shared stack (bucket, tables, topics, DLQ).
# Use them as local.core.<output>, e.g. local.core.lake_bucket, local.core.tables.stations
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

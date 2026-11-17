# Read the shared Core infrastructure outputs.
# AWS resources are deployed in us-east-1.
# Terraform state is stored in eu-north-1.

data "terraform_remote_state" "core" {
  backend = "s3"

  config = {
    bucket = var.state_bucket
    key    = "${var.region}/core/terraform.tfstate"
    region = "eu-north-1"
  }
}

locals {
  core = data.terraform_remote_state.core.outputs
}

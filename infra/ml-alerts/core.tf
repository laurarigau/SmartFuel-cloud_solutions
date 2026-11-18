# Read the shared Core infrastructure outputs.
# Same backend as scripts/deploy.sh: state bucket and resources in var.region.

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

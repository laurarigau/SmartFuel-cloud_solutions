terraform {
  required_version = ">= 1.10" # use_lockfile (S3 native locking)

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Partial configuration: bucket/key/region are passed with -backend-config
  # (see backend.hcl.example and .github/workflows/terraform.yml)
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project = var.project
      owner   = "core"
    }
  }
}

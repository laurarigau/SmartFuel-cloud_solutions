terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project = var.project
      owner   = "phase-a"
    }
  }
}

# Provider for the ingest Lambda and its schedule. Same region as the rest by
# default; var.ingest_region allows moving them if the Ministry API ever blocks
# a region (the Lambda can write into the lake bucket from any region).
provider "aws" {
  alias  = "ingest"
  region = var.ingest_region

  default_tags {
    tags = {
      project = var.project
      owner   = "phase-a"
    }
  }
}

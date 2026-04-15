terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.40"
    }
  }

  backend "s3" {
    bucket         = "{project}-terraform-state"
    key            = "terraform/state/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "{project}-terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.region
}

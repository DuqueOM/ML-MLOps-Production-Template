# CRITICAL: this state controls production. ADR-011 reviewers required.
bucket         = "{project}-tfstate-prod"
key            = "ml-mlops/prod/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "{project}-tfstate-lock-prod"
encrypt        = true

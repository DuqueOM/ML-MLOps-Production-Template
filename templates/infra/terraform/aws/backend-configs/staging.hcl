bucket         = "{project}-tfstate-staging"
key            = "ml-mlops/staging/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "{project}-tfstate-lock-staging"
encrypt        = true

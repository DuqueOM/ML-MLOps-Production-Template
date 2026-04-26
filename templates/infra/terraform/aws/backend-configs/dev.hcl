# Terraform backend config — AWS / dev
# Used by: terraform -chdir=templates/infra/terraform/aws init \
#            -backend-config=backend-configs/dev.hcl
#
# Audit High-6: state is namespaced by env. Bucket and DynamoDB lock table
# are pre-created out-of-band. See docs/runbooks/terraform-state-bootstrap.md.

bucket         = "{project}-tfstate-dev"
key            = "ml-mlops/dev/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "{project}-tfstate-lock-dev"
encrypt        = true

# Terraform backend config — GCP / dev
# Used by: terraform -chdir=templates/infra/terraform/gcp init \
#            -backend-config=backend-configs/dev.hcl
#
# Audit High-6: state is namespaced by env so a dev apply cannot
# mutate prod state. The bucket itself is pre-created out-of-band
# (chicken-and-egg). See docs/runbooks/terraform-state-bootstrap.md.

bucket = "{project}-tfstate-dev"
prefix = "ml-mlops/dev"

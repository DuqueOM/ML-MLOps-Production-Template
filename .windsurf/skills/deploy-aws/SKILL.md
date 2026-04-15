---
description: Deploy ML service to EKS with Kustomize overlays and IRSA
whenToUse: When deploying a service to AWS EKS cluster
---

# Deploy to EKS

## Pre-Flight Checklist

- [ ] Verify context: `kubectl config current-context` must be EKS cluster
- [ ] Docker image built and pushed to ECR
- [ ] Kustomize overlay patched with correct image tag
- [ ] Terraform applied for any new infrastructure
- [ ] Model artifact uploaded to S3
- [ ] All tests passing in CI

## Step 1: Verify Cluster Context

```bash
kubectl config current-context
# Expected: arn:aws:eks:{REGION}:{ACCOUNT}:cluster/{CLUSTER_NAME}
```

Switch context:
```bash
aws eks update-kubeconfig --name {CLUSTER} --region {REGION}
```

## Step 2: Build and Push Image

```bash
export VERSION=v{X.Y.Z}
export SHA=$(git rev-parse --short HEAD)
export REGISTRY={ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{REPO}

# Authenticate to ECR
aws ecr get-login-password --region {REGION} | docker login --username AWS --password-stdin ${REGISTRY}

docker build -t ${REGISTRY}/{service}:${VERSION} -t ${REGISTRY}/{service}:sha-${SHA} .
docker push ${REGISTRY}/{service}:${VERSION}
docker push ${REGISTRY}/{service}:sha-${SHA}
```

## Step 3: Update Kustomize Overlay

```yaml
# k8s/overlays/aws/kustomization.yaml
images:
  - name: {service}-predictor
    newName: {ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{REPO}/{service}
    newTag: {VERSION}
```

## Step 4: Apply Manifests

```bash
kubectl apply -k k8s/overlays/aws/
kubectl rollout status deployment/{service}-predictor -n {namespace} --timeout=300s
```

## Step 5: Smoke Test

```bash
export SVC_URL=$(kubectl get svc {service}-service -n {namespace} -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

curl -f http://${SVC_URL}/health
curl -X POST http://${SVC_URL}/predict \
  -H "Content-Type: application/json" \
  -d '{"feature_a": 1.0, "feature_b": "A"}'
```

## Step 6: Verify IRSA

```bash
# Check SA annotation
kubectl get serviceaccount {service}-sa -n {namespace} -o yaml | grep "eks.amazonaws.com/role-arn"

# Test S3 access from pod
kubectl exec -it {pod} -n {namespace} -- aws s3 ls s3://{model-bucket}/
```

## IRSA Troubleshooting

If S3 access fails:
1. Verify OIDC provider: `aws eks describe-cluster --name {CLUSTER} --query "cluster.identity.oidc"`
2. Verify trust policy on the IAM role allows the service account
3. Verify the role has S3 read permissions on the model bucket
4. Restart the pod (IRSA tokens are injected at pod creation)

## Rollback

```bash
kubectl rollout undo deployment/{service}-predictor -n {namespace}
kubectl rollout status deployment/{service}-predictor -n {namespace}
```

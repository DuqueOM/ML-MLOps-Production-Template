---
description: Deploy ML service to GKE with Kustomize overlays and Workload Identity
whenToUse: When deploying a service to GCP GKE cluster
---

# Deploy to GKE

## Pre-Flight Checklist

- [ ] Verify context: `kubectl config current-context` must be GKE cluster
- [ ] Docker image built and pushed to Artifact Registry
- [ ] Kustomize overlay patched with correct image tag
- [ ] Terraform applied for any new infrastructure
- [ ] Model artifact uploaded to GCS
- [ ] All tests passing in CI

## Step 1: Verify Cluster Context

```bash
kubectl config current-context
# Expected: gke_{PROJECT_ID}_{REGION}_{CLUSTER_NAME}
```

NEVER proceed if context is wrong. Switch with:
```bash
gcloud container clusters get-credentials {CLUSTER} --region {REGION} --project {PROJECT}
```

## Step 2: Build and Push Image

```bash
# Tag with version and SHA
export VERSION=v{X.Y.Z}
export SHA=$(git rev-parse --short HEAD)
export REGISTRY={REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}

docker build -t ${REGISTRY}/{service}:${VERSION} -t ${REGISTRY}/{service}:sha-${SHA} .
docker push ${REGISTRY}/{service}:${VERSION}
docker push ${REGISTRY}/{service}:sha-${SHA}
```

## Step 3: Update Kustomize Overlay

```bash
# k8s/overlays/gcp/kustomization.yaml
images:
  - name: {service}-predictor
    newName: {REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/{service}
    newTag: {VERSION}
```

## Step 4: Apply Manifests

```bash
kubectl apply -k k8s/overlays/gcp/
kubectl rollout status deployment/{service}-predictor -n {namespace} --timeout=300s
```

## Step 5: Smoke Test

```bash
# Get service URL
export SVC_URL=$(kubectl get ingress -n {namespace} -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')

# Health check
curl -f http://${SVC_URL}/health

# Test prediction
curl -X POST http://${SVC_URL}/predict \
  -H "Content-Type: application/json" \
  -d '{"feature_a": 1.0, "feature_b": "A"}'
```

## Step 6: Verify Monitoring

- [ ] Prometheus scraping `/metrics` from new pods
- [ ] Grafana dashboard showing new version
- [ ] No alert firing in AlertManager

## Rollback (if needed)

```bash
kubectl rollout undo deployment/{service}-predictor -n {namespace}
kubectl rollout status deployment/{service}-predictor -n {namespace}
```

## Workload Identity Verification

```bash
# Verify SA annotation
kubectl get serviceaccount {service}-sa -n {namespace} -o yaml | grep "iam.gke.io"

# Test GCS access from pod
kubectl exec -it {pod} -n {namespace} -- gsutil ls gs://{model-bucket}/
```

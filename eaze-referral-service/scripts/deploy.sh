#!/usr/bin/env bash
# Deploys eaze-referral-service: applies config, runs the migration Job to completion, THEN
# rolls out the Deployment. Plain Kubernetes manifests have no native "run this Job first" hook
# (that's a Helm feature) — this script is that ordering, made explicit and re-runnable.
#
# Usage: IMAGE=registry.example.com/eaze-referral-service:1.2.3 ./scripts/deploy.sh
set -euo pipefail

: "${IMAGE:?Set IMAGE to the image tag to deploy, e.g. IMAGE=ghcr.io/you/eaze-referral-service:1.2.3}"
NAMESPACE=eaze-referral
KUBECTL="${KUBECTL:-kubectl}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR/../k8s"

echo "==> Applying namespace and config"
"$KUBECTL" apply -f "$K8S_DIR/00-namespace.yaml"
"$KUBECTL" apply -f "$K8S_DIR/10-configmap.yaml"

if [ -f "$K8S_DIR/11-secret.yaml" ]; then
  "$KUBECTL" apply -f "$K8S_DIR/11-secret.yaml"
else
  echo "!! $K8S_DIR/11-secret.yaml not found — copy 11-secret.example.yaml, fill in DATABASE_URL," \
       "and apply it yourself (or via your secret manager) before continuing." >&2
  exit 1
fi

echo "==> Running migration Job (image: $IMAGE)"
"$KUBECTL" delete job eaze-referral-migrate -n "$NAMESPACE" --ignore-not-found
IMAGE="$IMAGE" envsubst < "$K8S_DIR/20-migration-job.yaml" | "$KUBECTL" apply -f -
"$KUBECTL" wait --for=condition=complete job/eaze-referral-migrate -n "$NAMESPACE" --timeout=180s

echo "==> Rolling out the API Deployment"
IMAGE="$IMAGE" envsubst < "$K8S_DIR/30-deployment.yaml" | "$KUBECTL" apply -f -
"$KUBECTL" apply -f "$K8S_DIR/31-service.yaml"
if [ -f "$K8S_DIR/32-hpa.yaml" ]; then
  "$KUBECTL" apply -f "$K8S_DIR/32-hpa.yaml"
fi
"$KUBECTL" rollout status deployment/eaze-referral-api -n "$NAMESPACE" --timeout=180s

echo "==> Done"

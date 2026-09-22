#!/usr/bin/env bash
# Deploys eaze-referral-service: applies config, runs the migration Job to completion, THEN
# rolls out the Deployment. Plain Kubernetes manifests have no native "run this Job first" hook
# (that's a Helm feature) — this script is that ordering, made explicit and re-runnable.
#
# Same image, two independent reward tiers, picked by TIER (see k8s/tier-1000/ and
# k8s/tier-500/ — each is its own namespace, ConfigMap, and Deployment/Service, so the two run
# side by side without interfering). There is no default/un-tiered deployment — TIER is required.
#
# Usage: IMAGE=registry.example.com/eaze-referral-service:1.2.3 TIER=1000 ./scripts/deploy.sh
#        IMAGE=registry.example.com/eaze-referral-service:1.2.3 TIER=500 ./scripts/deploy.sh
set -euo pipefail

: "${IMAGE:?Set IMAGE to the image tag to deploy, e.g. IMAGE=ghcr.io/you/eaze-referral-service:1.2.3}"
: "${TIER:?Set TIER to 1000 or 500 — there is no default/un-tiered deployment}"
case "$TIER" in
  1000|500) ;;
  *) echo "!! TIER must be 1000 or 500, got: $TIER" >&2; exit 1 ;;
esac
NAMESPACE="eaze-referral-$TIER"
KUBECTL="${KUBECTL:-kubectl}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR/../k8s/tier-$TIER"

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

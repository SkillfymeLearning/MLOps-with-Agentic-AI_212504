#!/usr/bin/env bash
# scripts/ci-deploy.sh
#
# Unified deployment script for GitHub Actions CI.
# Single source of truth for deploy/rollback/promote logic.
#
# Usage:
#   ./scripts/ci-deploy.sh staging [--dry-run]
#   ./scripts/ci-deploy.sh prod [--dry-run]
#
# Environment variables (set by CI):
#   REGISTRY       - Container registry (e.g., registry.example.com/mnist_tf)
#   NS             - Kubernetes namespace (e.g., kubeflow)
#   CONFIG         - Path to config file (e.g., config/ml-model-versions.yaml)
#   GITHUB_ACTOR   - User who triggered the workflow
#   PR_NUMBER      - Pull request number (optional)

set -euo pipefail

# ── Parse arguments ──────────────────────────────────────────────────────────
FLOW="${1:-staging}"
DRY_RUN=false
FORCE_ROLLBACK=false
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=true ;;
    --rollback) FORCE_ROLLBACK=true ;;
  esac
done

# ── Defaults ─────────────────────────────────────────────────────────────────
REGISTRY="${REGISTRY:-mnist_tf}"
NS="${NS:-kubeflow}"
CONFIG="${CONFIG:-config/ml-model-versions.yaml}"
ACTOR="${GITHUB_ACTOR:-$(git config user.name || echo "ci")}"
PR_NUMBER="${PR_NUMBER:-0}"

# ── Check config file exists ─────────────────────────────────────────────────
if [[ ! -f "${CONFIG}" ]]; then
  echo "ERROR: ${CONFIG} not found."
  exit 1
fi

# ── Read config values ───────────────────────────────────────────────────────
echo "Reading config from ${CONFIG}..."

# Helper to read nested values using grep/sed (no yq dependency)
read_block_val() {
  local block="$1"
  local key="$2"
  local result
  result=$(sed -n "/^${block}:/,/^[a-z]/p" "${CONFIG}" 2>/dev/null | grep -E "^\s*${key}:" 2>/dev/null | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs 2>/dev/null | head -1 || echo "")
  echo "${result}"
}

# dev block
DEV_SHA=$(read_block_val "dev" "sha")
DEV_TAG=$(read_block_val "dev" "tag")

# stable block
STABLE_SHA=$(read_block_val "stable" "sha")
STABLE_TAG=$(read_block_val "stable" "tag")
STABLE_PROMOTED_AT=$(read_block_val "stable" "promoted_at")
STABLE_PROMOTED_BY=$(read_block_val "stable" "promoted_by")

# last_stable block
LAST_STABLE_SHA=$(read_block_val "last_stable" "sha")
LAST_STABLE_TAG=$(read_block_val "last_stable" "tag")
LAST_STABLE_PROMOTED_AT=$(read_block_val "last_stable" "promoted_at")
LAST_STABLE_PROMOTED_BY=$(read_block_val "last_stable" "promoted_by")

# canary block
CANARY_SHA=$(read_block_val "canary" "sha")
CANARY_TAG=$(read_block_val "canary" "tag")
CANARY_WEIGHT=$(read_block_val "canary" "weight")

# last_rollback block
LR_SHA=$(read_block_val "last_rollback" "evicted_sha" || true)
LR_REASON=$(read_block_val "last_rollback" "reason" || true)
LR_AT=$(read_block_val "last_rollback" "at" || true)
LR_BY=$(read_block_val "last_rollback" "by" || true)

echo "  dev.sha         = '${DEV_SHA}'"
echo "  stable.sha      = '${STABLE_SHA:-<empty>}'"
echo "  last_stable.sha = '${LAST_STABLE_SHA:-<empty>}'"
echo "  canary.sha      = '${CANARY_SHA:-<empty>}'"
echo "  canary.weight   = '${CANARY_WEIGHT:-0}'"

# ── Decide action based on flow ──────────────────────────────────────────────
echo ""
echo "Deciding action for ${FLOW}..."

# Check for forced rollback first
if [[ "${FORCE_ROLLBACK}" == "true" ]]; then
  if [[ -z "${CANARY_SHA}" || "${CANARY_SHA}" == "null" ]]; then
    ACTION="noop"
    echo "  → ACTION: NO-OP (nothing to rollback)"
    echo "    canary.sha is already empty"
  else
    ACTION="rollback"
    TEMPLATE="k8s/rollback.yaml.tpl"
    echo "  → ACTION: FORCED ROLLBACK"
    echo "    --rollback flag provided, clearing canary.sha='${CANARY_SHA}'"
  fi
elif [[ "${FLOW}" == "staging" ]]; then
  # STAGING logic:
  # 1. If canary.sha == dev.sha → already deployed, NO-OP
  # 2. If dev.sha != stable.sha → DEPLOY new canary
  # 3. If dev.sha == stable.sha AND canary empty → NO-OP
  # 4. If dev.sha == stable.sha AND canary exists → ROLLBACK
  if [[ "${CANARY_SHA}" == "${DEV_SHA}" && -n "${CANARY_SHA}" ]]; then
    ACTION="noop"
    echo "  → ACTION: NO-OP (canary already deployed)"
    echo "    canary.sha='${CANARY_SHA}' already matches dev.sha"
  elif [[ "${DEV_SHA}" != "${STABLE_SHA}" ]]; then
    ACTION="deploy"
    TEMPLATE="k8s/canary-20.yaml.tpl"
    echo "  → ACTION: DEPLOY (canary-20)"
    echo "    dev.sha='${DEV_SHA}' differs from stable.sha='${STABLE_SHA}'"
  elif [[ -z "${CANARY_SHA}" ]]; then
    ACTION="noop"
    echo "  → ACTION: NO-OP (already in sync)"
    echo "    dev.sha='${DEV_SHA}' equals stable.sha and canary is empty"
  else
    ACTION="rollback"
    TEMPLATE="k8s/rollback.yaml.tpl"
    echo "  → ACTION: ROLLBACK"
    echo "    dev.sha='${DEV_SHA}' equals stable.sha, clearing canary.sha='${CANARY_SHA}'"
  fi

elif [[ "${FLOW}" == "prod" ]]; then
  # PROD: Promote canary to stable
  if [[ -z "${CANARY_SHA}" || "${CANARY_SHA}" == "null" ]]; then
    ACTION="noop"
    echo "  → ACTION: NO-OP (nothing to promote)"
    echo "    canary.sha is empty"
  else
    ACTION="promote"
    TEMPLATE="k8s/promote.yaml.tpl"
    echo "  → ACTION: PROMOTE"
    echo "    promoting canary.sha='${CANARY_SHA}' to stable"
  fi
fi

# ── Exit if NO-OP ────────────────────────────────────────────────────────────
if [[ "${ACTION}" == "noop" ]]; then
  echo ""
  echo "No changes to apply."
  exit 0
fi

# ── Check template exists ────────────────────────────────────────────────────
if [[ ! -f "${TEMPLATE}" ]]; then
  echo "ERROR: Template ${TEMPLATE} not found."
  exit 1
fi

# ── Render template ──────────────────────────────────────────────────────────
echo ""
echo "Rendering ${TEMPLATE}..."

NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Common exports
export STABLE_IMAGE="${REGISTRY}:${STABLE_TAG:-latest}"
export STABLE_SHA="${STABLE_SHA}"
export STABLE_TAG="${STABLE_TAG}"
export STABLE_PROMOTED_AT="${STABLE_PROMOTED_AT}"
export STABLE_PROMOTED_BY="${STABLE_PROMOTED_BY}"
export LAST_STABLE_SHA="${LAST_STABLE_SHA:-}"
export LAST_STABLE_TAG="${LAST_STABLE_TAG:-}"
export LAST_STABLE_PROMOTED_AT="${LAST_STABLE_PROMOTED_AT:-}"
export LAST_STABLE_PROMOTED_BY="${LAST_STABLE_PROMOTED_BY:-}"
export LR_SHA="${LR_SHA:-}"
export LR_REASON="${LR_REASON:-}"
export LR_AT="${LR_AT:-}"
export LR_BY="${LR_BY:-}"

if [[ "${ACTION}" == "deploy" ]]; then
  export CANARY_IMAGE="${REGISTRY}:${DEV_TAG}"
  export CANARY_SHA="${DEV_SHA}"
  export CANARY_TAG="${DEV_TAG}"
  export DEPLOYED_AT="${NOW}"
  export DEPLOYED_BY="${ACTOR}"
  export PR_NUMBER="${PR_NUMBER}"
elif [[ "${ACTION}" == "rollback" ]]; then
  export CANARY_IMAGE="${REGISTRY}:${CANARY_TAG}"
  export EVICTED_SHA="${CANARY_SHA}"
  export ROLLBACK_REASON="revert PR #${PR_NUMBER}"
  export ROLLBACK_AT="${NOW}"
  export ROLLBACK_BY="${ACTOR}"
elif [[ "${ACTION}" == "promote" ]]; then
  export CANARY_IMAGE="${REGISTRY}:${CANARY_TAG}"
  export CANARY_SHA="${CANARY_SHA}"
  export CANARY_TAG="${CANARY_TAG}"
  export PROMOTED_AT="${NOW}"
  export PROMOTED_BY="${ACTOR}"
fi

RENDERED=$(envsubst < "${TEMPLATE}")

# ── Apply or dry-run ─────────────────────────────────────────────────────────
if [[ "${DRY_RUN}" == "true" ]]; then
  echo ""
  echo "=== DRY-RUN: Would apply ==="
  echo "${RENDERED}"
  echo "==========================="
else
  echo ""
  echo "Applying to namespace: ${NS}..."
  echo "${RENDERED}" | kubectl apply -f - -n "${NS}"
  
  # Delete v2 InferenceService for rollback/promote
  if [[ "${ACTION}" == "rollback" || "${ACTION}" == "promote" ]]; then
    echo "Deleting canary InferenceService..."
    kubectl delete isvc canary-digits-server-v2 -n "${NS}" --ignore-not-found
  fi
  
  echo ""
  echo "✓ ${ACTION} completed successfully!"
fi

# ── Output action for GitHub Actions ─────────────────────────────────────────
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "action=${ACTION}" >> "${GITHUB_OUTPUT}"
  echo "canary_sha=${CANARY_SHA}" >> "${GITHUB_OUTPUT}"
  echo "dev_sha=${DEV_SHA}" >> "${GITHUB_OUTPUT}"
  echo "stable_sha=${STABLE_SHA}" >> "${GITHUB_OUTPUT}"
fi

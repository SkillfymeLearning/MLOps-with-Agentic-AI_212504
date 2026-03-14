#!/usr/bin/env bash
# scripts/test-staging-flow.sh
#
# Local simulation of the CI jobs from .github/workflows/test.yaml
# Run this to test deploy/rollback/promote logic locally.
#
# Usage:
#   ./scripts/test-staging-flow.sh [staging|prod] [--sync] [--dry-run|--apply|--configmap-only]
#
# Examples:
#   ./scripts/test-staging-flow.sh staging --dry-run          # Test staging (dry run)
#   ./scripts/test-staging-flow.sh staging --configmap-only   # Apply only ConfigMap to cluster
#   ./scripts/test-staging-flow.sh --sync --configmap-only    # Sync + apply ConfigMap
#   ./scripts/test-staging-flow.sh prod --dry-run             # Test prod promotion
#   ./scripts/test-staging-flow.sh --sync                     # Just sync config from cluster
#
# Options:
#   staging          Simulate staging-apply job (deploy or rollback)
#   prod             Simulate prod-promote job (promote canary to stable)
#   --sync           Run gen.sh first to sync config from cluster's ConfigMap
#   --dry-run        Print the rendered YAML without applying to cluster
#   --apply          Apply the rendered YAML to cluster
#   --configmap-only Apply only the ConfigMap (skip InferenceService etc.)

set -euo pipefail

# Parse arguments
FLOW="staging"
DRY_RUN=true
SYNC=false
CONFIGMAP_ONLY=false
FORCE_ROLLBACK=false

for arg in "$@"; do
  case "${arg}" in
    staging|prod) FLOW="${arg}" ;;
    --dry-run) DRY_RUN=true ;;
    --apply) DRY_RUN=false ;;
    --sync) SYNC=true ;;
    --configmap-only) CONFIGMAP_ONLY=true; DRY_RUN=false ;;
    --rollback) FORCE_ROLLBACK=true ;; # New argument
  esac
done

CONFIG="config/ml-model-versions.yaml"
REGISTRY="mnist_tf"
NS="kubeflow"
GEN_SCRIPT="scripts/generate-ml-config.sh"

FLOW_UPPER=$(echo "${FLOW}" | tr '[:lower:]' '[:upper:]')
echo "═══════════════════════════════════════════════════════════════════════"
echo " LOCAL ${FLOW_UPPER} FLOW TEST"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
if [[ "${FORCE_ROLLBACK}" == "true" ]]; then
  echo "[Rollback Prep] Setting up rollback conditions..."
  
  # Step 1: Sync from cluster to get current state (including canary.sha)
  echo "  [1/3] Syncing config from cluster..."
  TEMP_CHANGE=false
  if ! git diff --cached --name-only 2>/dev/null | grep -qE '^(model/|Dockerfile\.model)'; then
    echo "# rollback-sync $(date +%s)" >> model/model.txt
    git add model/model.txt
    TEMP_CHANGE=true
  fi
  bash "${GEN_SCRIPT}"
  if [[ "${TEMP_CHANGE}" == "true" ]]; then
    git restore --staged model/model.txt
    git checkout model/model.txt 2>/dev/null || true
  fi
  
  # Step 2: Read stable SHA and reset git to it
  CURRENT_STABLE=$(sed -n '/^stable:/,/^[a-z]/p' "${CONFIG}" | grep "sha:" | awk '{print $2}' | tr -d '"')
  if [[ -z "${CURRENT_STABLE}" ]]; then
    echo "ERROR: Could not find stable.sha in ${CONFIG}. Cannot rollback."
    exit 1
  fi
  echo "  [2/3] Resetting git HEAD to stable: ${CURRENT_STABLE}"
  git reset --hard "${CURRENT_STABLE}"
  
  # Step 3: Re-sync so dev.sha reflects the new git HEAD (= stable.sha)
  echo "  [3/3] Re-syncing config (dev.sha will now equal stable.sha)..."
  TEMP_CHANGE=false
  if ! git diff --cached --name-only 2>/dev/null | grep -qE '^(model/|Dockerfile\.model)'; then
    echo "# rollback-resync $(date +%s)" >> model/model.txt
    git add model/model.txt
    TEMP_CHANGE=true
  fi
  bash "${GEN_SCRIPT}"
  if [[ "${TEMP_CHANGE}" == "true" ]]; then
    git restore --staged model/model.txt
    git checkout model/model.txt 2>/dev/null || true
  fi
  echo "  ✓ Rollback conditions set: dev.sha=stable.sha, canary.sha preserved from cluster"
  echo ""
fi

# ── Sync from cluster if requested ───────────────────────────────────────────
if [[ "${SYNC}" == "true" && "${FORCE_ROLLBACK}" != "true" ]]; then
  echo "[0/4] Syncing config from cluster using ${GEN_SCRIPT}..."
  if [[ ! -x "${GEN_SCRIPT}" ]]; then
    echo "ERROR: ${GEN_SCRIPT} not found or not executable."
    exit 1
  fi
  
  # Temporarily stage a model file to satisfy gen.sh guards
  TEMP_CHANGE=false
  if ! git diff --cached --name-only 2>/dev/null | grep -qE '^(model/|Dockerfile\.model)'; then
    echo "  (Staging model/model.txt temporarily to trigger gen.sh)"
    echo "# sync $(date +%s)" >> model/model.txt
    git add model/model.txt
    TEMP_CHANGE=true
  fi
  
  # Run gen.sh to fetch from cluster and update config
  bash "${GEN_SCRIPT}"
  
  # Unstage if we made a temporary change
  if [[ "${TEMP_CHANGE}" == "true" ]]; then
    git restore --staged model/model.txt
    git checkout model/model.txt 2>/dev/null || true
  fi
  echo ""
fi

# ── Check config file exists ─────────────────────────────────────────────────
if [[ ! -f "${CONFIG}" ]]; then
  echo "ERROR: ${CONFIG} not found."
  echo "       Run with --sync to fetch from cluster, or run pre-commit hook first."
  exit 1
fi

# ── Read config values (same as CI) ──────────────────────────────────────────
echo "[1/4] Reading config from ${CONFIG}..."

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

echo "  dev.sha         = '${DEV_SHA}'"
echo "  dev.tag         = '${DEV_TAG}'"
echo "  stable.sha      = '${STABLE_SHA:-<empty>}'"
echo "  stable.tag      = '${STABLE_TAG:-<empty>}'"
echo "  last_stable.sha = '${LAST_STABLE_SHA:-<empty>}'"
echo "  canary.sha      = '${CANARY_SHA:-<empty>}'"
echo "  canary.tag      = '${CANARY_TAG:-<empty>}'"
echo "  canary.weight   = '${CANARY_WEIGHT:-0}'"
echo ""

# ── Decide action based on flow ──────────────────────────────────────────────
echo "[2/4] Deciding action..."
if [[ "${FLOW}" == "staging" ]]; then
  # STAGING logic:
  # 1. If canary.sha == dev.sha → already deployed, NO-OP
  # 2. If dev.sha != stable.sha AND canary.sha != dev.sha → DEPLOY new canary
  # 3. If dev.sha == stable.sha → ROLLBACK (clear canary)
  if [[ "${CANARY_SHA}" == "${DEV_SHA}" && -n "${CANARY_SHA}" ]]; then
    ACTION="noop"
    echo "  → ACTION: NO-OP (canary already deployed)"
    echo "    Reason: canary.sha='${CANARY_SHA}' already matches dev.sha"
    echo ""
    echo "  ╔════════════════════════════════════════════════════════════════╗"
    echo "  ║  CURRENT CANARY (already running)                              ║"
    echo "  ╠════════════════════════════════════════════════════════════════╣"
    echo "  ║  canary.sha    : ${CANARY_SHA}"
    echo "  ║  canary.weight : ${CANARY_WEIGHT:-20}%"
    echo "  ╠════════════════════════════════════════════════════════════════╣"
    echo "  ║  Nothing to deploy. Change model or promote to prod.          ║"
    echo "  ╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════"
    echo " DONE (no changes)"
    echo "═══════════════════════════════════════════════════════════════════════"
    exit 0
  elif [[ "${DEV_SHA}" != "${STABLE_SHA}" ]]; then
    ACTION="deploy"
    TEMPLATE="k8s/canary-20.yaml.tpl"
    echo "  → ACTION: DEPLOY (canary-20)"
    echo "    Reason: dev.sha='${DEV_SHA}' differs from stable.sha='${STABLE_SHA}'"
  elif [[ -z "${CANARY_SHA}" ]]; then
    # dev.sha == stable.sha AND canary is already empty → nothing to do
    ACTION="noop"
    echo "  → ACTION: NO-OP (already in sync)"
    echo "    Reason: dev.sha='${DEV_SHA}' equals stable.sha and canary is empty"
    echo ""
    echo "  ╔════════════════════════════════════════════════════════════════╗"
    echo "  ║  CURRENT STABLE MODEL                                          ║"
    echo "  ╠════════════════════════════════════════════════════════════════╣"
    echo "  ║  stable.sha    : ${STABLE_SHA}"
    echo "  ║  stable.tag    : ${STABLE_TAG}"
    echo "  ╠════════════════════════════════════════════════════════════════╣"
    echo "  ║  No canary running. Deploy a new model to staging.            ║"
    echo "  ╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════"
    echo " DONE (no changes)"
    echo "═══════════════════════════════════════════════════════════════════════"
    exit 0
  else
    # dev.sha == stable.sha AND canary exists → rollback (clear canary)
    ACTION="rollback"
    TEMPLATE="k8s/rollback.yaml.tpl"
    echo "  → ACTION: ROLLBACK"
    echo "    Reason: dev.sha='${DEV_SHA}' equals stable.sha, clearing canary.sha='${CANARY_SHA}'"
  fi
elif [[ "${FLOW}" == "prod" ]]; then
  # PROD: Promote canary to stable
  if [[ -z "${CANARY_SHA}" || "${CANARY_SHA}" == "null" ]]; then
    ACTION="noop"
    echo "  → ACTION: NO-OP (already up to date)"
    echo ""
    echo "  ╔════════════════════════════════════════════════════════════════╗"
    echo "  ║  CURRENT STABLE MODEL                                          ║"
    echo "  ╠════════════════════════════════════════════════════════════════╣"
    echo "  ║  stable.sha    : ${STABLE_SHA:-<none>}"
    echo "  ║  stable.tag    : ${STABLE_TAG:-<none>}"
    echo "  ║  promoted_at   : ${STABLE_PROMOTED_AT:-<unknown>}"
    echo "  ║  promoted_by   : ${STABLE_PROMOTED_BY:-<unknown>}"
    echo "  ╠════════════════════════════════════════════════════════════════╣"
    echo "  ║  No canary to promote. Deploy to staging first.               ║"
    echo "  ╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════"
    echo " DONE (no changes)"
    echo "═══════════════════════════════════════════════════════════════════════"
    exit 0
  fi
  ACTION="promote"
  TEMPLATE="k8s/promote.yaml.tpl"
  echo "  → ACTION: PROMOTE"
  echo "    Reason: promoting canary.sha='${CANARY_SHA}' to stable"
fi
echo ""

# ── Check template exists ────────────────────────────────────────────────────
if [[ ! -f "${TEMPLATE}" ]]; then
  echo "ERROR: Template ${TEMPLATE} not found."
  exit 1
fi

# ── Render template ──────────────────────────────────────────────────────────
echo "[3/4] Rendering ${TEMPLATE}..."

NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ACTOR=$(git config user.name || echo "local-test")

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
export LR_SHA=""
export LR_REASON=""
export LR_AT=""
export LR_BY=""

if [[ "${ACTION}" == "deploy" ]]; then
  # Deploy: new canary from dev
  export CANARY_IMAGE="${REGISTRY}:${DEV_TAG}"
  export CANARY_SHA="${DEV_SHA}"
  export CANARY_TAG="${DEV_TAG}"
  export DEPLOYED_AT="${NOW}"
  export DEPLOYED_BY="${ACTOR}"
  export PR_NUMBER="local-test"
elif [[ "${ACTION}" == "rollback" ]]; then
  # Rollback: evict canary
  export CANARY_IMAGE="${REGISTRY}:${CANARY_TAG}"
  export EVICTED_SHA="${CANARY_SHA}"
  export ROLLBACK_REASON="local test rollback"
  export ROLLBACK_AT="${NOW}"
  export ROLLBACK_BY="${ACTOR}"
elif [[ "${ACTION}" == "promote" ]]; then
  # Promote: canary becomes stable
  export CANARY_IMAGE="${REGISTRY}:${CANARY_TAG}"
  export CANARY_SHA="${CANARY_SHA}"
  export CANARY_TAG="${CANARY_TAG}"
  export PROMOTED_AT="${NOW}"
  export PROMOTED_BY="${ACTOR}"
fi

RENDERED=$(envsubst < "${TEMPLATE}")

echo ""
echo "───────────────────────────────────────────────────────────────────────"
echo " RENDERED YAML:"
echo "───────────────────────────────────────────────────────────────────────"
echo "${RENDERED}"
echo "───────────────────────────────────────────────────────────────────────"
echo ""

# ── Extract ConfigMap only if requested ──────────────────────────────────────
if [[ "${CONFIGMAP_ONLY}" == "true" ]]; then
  # Extract just the ConfigMap (everything from apiVersion: v1 to next ---)
  CONFIGMAP_YAML=$(echo "${RENDERED}" | awk '/^apiVersion: v1/{found=1} found{print} /^kind: ConfigMap/{cm=1} cm && /^---/{exit}')
  echo ""
  echo "───────────────────────────────────────────────────────────────────────"
  echo " CONFIGMAP ONLY:"
  echo "───────────────────────────────────────────────────────────────────────"
  echo "${CONFIGMAP_YAML}"
  echo "───────────────────────────────────────────────────────────────────────"
fi

# ── Apply or dry-run ─────────────────────────────────────────────────────────
echo "[4/4] Applying..."

# Tag docker image with the respective tag
if [[ "${ACTION}" == "deploy" ]]; then
  echo "  Tagging docker image: ${REGISTRY}:latest → ${REGISTRY}:${DEV_TAG}"
  docker tag "${REGISTRY}:latest" "${REGISTRY}:${DEV_TAG}" 2>/dev/null || \
    echo "  (Image tagging skipped - ${REGISTRY}:latest not found locally)"
elif [[ "${ACTION}" == "promote" ]]; then
  echo "  Tagging docker image: ${REGISTRY}:${CANARY_TAG} → ${REGISTRY}:stable"
  docker tag "${REGISTRY}:${CANARY_TAG}" "${REGISTRY}:stable" 2>/dev/null || \
    echo "  (Image tagging skipped - ${REGISTRY}:${CANARY_TAG} not found locally)"
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "  [DRY-RUN] Would apply to namespace: ${NS}"
  echo "  [DRY-RUN] Run with --apply or --configmap-only to apply"
elif [[ "${CONFIGMAP_ONLY}" == "true" ]]; then
  echo "  Applying ConfigMap only to namespace: ${NS}"
  echo "${CONFIGMAP_YAML}" | kubectl apply -f - -n "${NS}"
  echo ""
  echo "  ✓ ConfigMap applied successfully!"
  echo ""
  echo "  Verifying ConfigMap:"
  kubectl get configmap canary-state -n "${NS}" -o yaml | head -40
else
  echo "  Applying all resources to namespace: ${NS}"
  echo "${RENDERED}" | kubectl apply -f - -n "${NS}"
  echo ""
  echo "  ✓ Applied successfully!"
  
  if [[ "${ACTION}" == "rollback" || "${ACTION}" == "promote" ]]; then
    echo "  Deleting canary InferenceService..."
    kubectl delete isvc canary-digits-server-v2 -n "${NS}" --ignore-not-found
  fi
fi

# ── Post-apply sync: update local yaml to match cluster ─────────────────────
if [[ "${DRY_RUN}" == "false" ]]; then
  echo ""
  echo "[5/5] Syncing local config from cluster..."
  
  # Temporarily stage a model file to satisfy gen.sh guards
  TEMP_CHANGE=false
  if ! git diff --cached --name-only 2>/dev/null | grep -qE '^(model/|Dockerfile\.model)'; then
    echo "# post-sync $(date +%s)" >> model/model.txt
    git add model/model.txt
    TEMP_CHANGE=true
  fi
  
  # Run gen.sh to update local yaml from cluster
  bash "${GEN_SCRIPT}"
  
  # Unstage if we made a temporary change
  if [[ "${TEMP_CHANGE}" == "true" ]]; then
    git restore --staged model/model.txt
    git checkout model/model.txt 2>/dev/null || true
  fi
  
  echo "  ✓ Local config updated to match cluster"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo " DONE"
echo "═══════════════════════════════════════════════════════════════════════"

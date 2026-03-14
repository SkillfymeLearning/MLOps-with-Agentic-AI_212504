# k8s/rollback.yaml.tpl
# Applied by CI: revert PR merged to staging
# Clears canary block, writes last-rollback-* so hook reads it next push
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: canary-state
  namespace: kubeflow
  labels:
    app: digits-server
data:
    state.yaml: |
      stable:
        sha: "$STABLE_SHA"
        tag: "$STABLE_TAG"
        promoted_at: "$STABLE_PROMOTED_AT"
        promoted_by: "$STABLE_PROMOTED_BY"
      last_stable:
        sha: "$LAST_STABLE_SHA"
        tag: "$LAST_STABLE_TAG"
        promoted_at: "$LAST_STABLE_PROMOTED_AT"
        promoted_by: "$LAST_STABLE_PROMOTED_BY"
      canary:
        sha: ""
        tag: ""
        weight: 0
      last_rollback:
        evicted_sha: "$EVICTED_SHA"
        reason: "$ROLLBACK_REASON"
        at: "$ROLLBACK_AT"
        by: "$ROLLBACK_BY"
      dev:
        sha: ""
        tag: ""
      updated_at: "$ROLLBACK_AT"
---
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: canary-digits-server
  namespace: kubeflow
  annotations:
    serving.kserve.io/revisionTag: "v1-stable-$STABLE_SHA"
    sidecar.istio.io/inject: "false"
    serving.kserve.io/deploymentMode: RawDeployment
  labels:
    canary-group: digits-server
    sha: "$STABLE_SHA"
spec:
  predictor:
    minReplicas: 4
    maxReplicas: 4
    containers:
    - name: kserve-container
      image: $STABLE_IMAGE
      command: ["python", "/app/server.py"]
      args: ["v1"]
      ports:
      - containerPort: 8686
        name: mnist-port
        protocol: TCP
      resources:
        requests:
          cpu: "1"
          memory: "2Gi"
        limits:
          cpu: "2"
          memory: "4Gi"
# v2 InferenceService deleted by CI after applying this

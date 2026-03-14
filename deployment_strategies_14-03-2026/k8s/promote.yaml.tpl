# k8s/promote.yaml.tpl
# Applied by CI: PR merged to prod
# Canary image becomes new stable, canary block cleared
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
        sha: "$CANARY_SHA"
        tag: "$CANARY_TAG"
        promoted_at: "$PROMOTED_AT"
        promoted_by: "$PROMOTED_BY"
      last_stable:
        sha: "$STABLE_SHA"
        tag: "$STABLE_TAG"
        promoted_at: "$STABLE_PROMOTED_AT"
        promoted_by: "$STABLE_PROMOTED_BY"
      canary:
        sha: ""
        tag: ""
        weight: 0
      dev:
        sha: ""
        tag: ""
      updated_at: "$PROMOTED_AT"
---
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: canary-digits-server
  namespace: kubeflow
  annotations:
    serving.kserve.io/revisionTag: "v1-stable-$CANARY_SHA"
    sidecar.istio.io/inject: "false"
    serving.kserve.io/deploymentMode: RawDeployment
  labels:
    canary-group: digits-server
    sha: "$CANARY_SHA"
spec:
  predictor:
    minReplicas: 4
    maxReplicas: 4
    containers:
    - name: kserve-container
      image: $CANARY_IMAGE
      command: ["python", "/app/server.py"]
      args: ["v2"]
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

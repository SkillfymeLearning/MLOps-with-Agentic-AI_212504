# k8s/canary-20.yaml.tpl
# Applied by CI: PR merged to staging (forward deploy)
# ConfigMap keys use hyphens — exactly what generate-ml-config.sh reads back next push
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
        sha: "$CANARY_SHA"
        tag: "$CANARY_TAG"
        weight: 20
        deployed_at: "$DEPLOYED_AT"
        deployed_by: "$DEPLOYED_BY"
      dev:
        sha: ""
        tag: ""
      updated_at: "$DEPLOYED_AT"
  
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
---
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: canary-digits-server-v2
  namespace: kubeflow
  annotations:
    serving.kserve.io/revisionTag: "v2-canary-$CANARY_SHA"
    sidecar.istio.io/inject: "false"
    serving.kserve.io/deploymentMode: RawDeployment
  labels:
    canary-group: digits-server
    sha: "$CANARY_SHA"
spec:
  predictor:
    minReplicas: 1
    maxReplicas: 1
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

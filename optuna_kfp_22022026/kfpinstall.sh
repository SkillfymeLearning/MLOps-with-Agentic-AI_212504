kubectl apply -k "./manifests/apps/pipeline/upstream/cluster-scoped-resources"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "./manifests/apps/pipeline/upstream/env/platform-agnostic"
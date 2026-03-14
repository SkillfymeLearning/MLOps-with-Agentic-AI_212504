# rdctl reset --k8s
# Version variables
# GATEWAY_API_VERSION=v1.2.1
# ISTIO_VERSION=1.27.1
# CERT_MANAGER_VERSION=v1.17.0

# echo "Installing Gateway API CRDs ..."
# kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml

# helm repo add istio https://istio-release.storage.googleapis.com/charts --force-update
# helm install istio-base istio/base -n istio-system --wait --set defaultRevision=default --create-namespace --version ${ISTIO_VERSION}
# helm install istiod istio/istiod -n istio-system --wait --version ${ISTIO_VERSION} \
#    --set proxy.autoInject=disabled \
#    --set-string pilot.podAnnotations."cluster-autoscaler\.kubernetes\.io/safe-to-evict"=true
# helm install istio-ingressgateway istio/gateway -n istio-system --version ${ISTIO_VERSION} \
#    --set-string podAnnotations."cluster-autoscaler\.kubernetes\.io/safe-to-evict"=true

# # Wait for the istio ingressgateway pod to be created
# sleep 10
# # Wait for istio ingressgateway to be ready
# kubectl wait --for=condition=Ready pod -l app=istio-ingressgateway -n istio-system --timeout=600s
# echo "😀 Successfully installed Istio"

# Install Cert Manager
CERT_MANAGER_VERSION=v1.17.0
helm repo add jetstack https://charts.jetstack.io --force-update
helm install \
   cert-manager jetstack/cert-manager \
   --namespace cert-manager \
   --create-namespace \
   --version ${CERT_MANAGER_VERSION} \
   --set crds.enabled=true
echo "😀 Successfully installed Cert Manager"
helm install kserve-crd oci://ghcr.io/kserve/charts/kserve-crd --version v0.15.2 --namespace kubeflow --create-namespace
kubectl apply --server-side --force-conflicts -k "github.com/kubeflow/manifests/applications/kserve/kserve?ref=v1.11-branch"
kubectl apply -f kserve-resources

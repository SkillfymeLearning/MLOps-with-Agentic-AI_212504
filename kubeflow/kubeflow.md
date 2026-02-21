
# Kubeflow Pipeline Architecture

## 1. Control Plane
These services manage the logic of creating, scheduling, and tracking your machine learning experiments:

- **ml-pipeline**: Main API server. Handles pipeline runs and uploads.
- **workflow-controller**: Argo Workflows. Watches for Workflow objects and orchestrates container execution in Kubernetes.
- **ml-pipeline-scheduledworkflow**: Manages recurring jobs (e.g., scheduled retraining).
- **ml-pipeline-persistenceagent**: Tracks container status and logs results in the database.

---

## 2. Metadata & Tracking
Tracks data lineage and experiment metadata:

- **metadata-grpc-deployment**: Backend for Kubeflow ML Metadata (MLMD). Stores artifacts and executions.
- **metadata-envoy-deployment**: Proxy for GRPC server, manages network traffic and protocol translation.
- **metadata-writer**: Listens to pipeline events and writes results to the Metadata database (for Lineage explorer).

---

## 3. Storage & Database
Foundation for pipeline state and files:

- **mysql**: Relational database for pipeline definitions, run history, and settings.
- **seaweedfs**: Distributed file system for pipeline artifacts (e.g., CSVs, models).
- **cache-server / cache-deployer**: Task Caching. Reuses results for identical pipeline steps.

---

## 4. UI & Visualization
User-facing components:

- **ml-pipeline-ui**: Web interface for pipeline management.
- **ml-pipeline-visualizationserver**: Generates charts (ROC, Confusion Matrix) for pipeline runs.
- **ml-pipeline-viewer-crd**: Launches custom viewers (e.g., TensorBoard) from Kubeflow UI.

---

## Summary Table

| Component                  | Responsibility         | Criticality                        |
|---------------------------|-----------------------|-------------------------------------|
| ml-pipeline                | API & Orchestration   | High (System fails without it)   |
| Argo (workflow-controller) | Container Execution   | High (Pipelines won't start)     |
| MySQL / SeaweedFS          | Data Storage          | High (State will be lost)        |
| Cache Server               | Performance           | Medium (Pipelines just run slower)|
| Visualization Server       | UI Charts             | Low (UI works, charts don't)     |



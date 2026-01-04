
## Installation

### Using uv (recommended)
```bash
# Basic MLflow installation
uv add mlflow

# MLflow with basic authentication
uv add "mlflow[auth]"

# MLflow with OIDC authentication
uv add "mlflow-oidc-auth[full]"
```

### Using pip
```bash
# Basic MLflow installation
pip install mlflow

# MLflow with basic authentication
pip install "mlflow[auth]"

# MLflow with OIDC authentication
pip install "mlflow-oidc-auth[full]"
```

## Configuration for Basic Auth
1. basic_auth.ini
2. For basic auth use start_mlflow_basic.sh
3. for oidc use start_mlflow.sh

### 1. Start MLflow Server


### 2. Create Users
# Or using Python script
python create_user.py

### 3. Configure Client Authentication
Once we have users created you can use 
export MLFLOW_TRACKING_USERNAME='<username>'
export MLFLOW_TRACKING_PASSWORD='<password>'
**In Python scripts:**
```python
import mlflow
import os

# Set tracking URI
tracking_uri = "http://localhost:8080/"  # Or http://host.docker.internal:8080/ for Docker
os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
os.environ["MLFLOW_TRACKING_USERNAME"] = "admin"
os.environ["MLFLOW_TRACKING_PASSWORD"] = "password@1234"

# Or use mlflow.set_tracking_uri()
mlflow.set_tracking_uri(tracking_uri)
```

**In terminal:**
```bash
export MLFLOW_TRACKING_URI=http://localhost:8080/
export MLFLOW_TRACKING_USERNAME=admin
export MLFLOW_TRACKING_PASSWORD=password@1234
```

### 4. Access MLflow UI
Navigate to: http://localhost:8080/
Login with username: admin, password: password@1234

## Common Issues

**Connection Refused:**
- Ensure server is bound to 0.0.0.0 (not 127.0.0.1)
- Check firewall settings
- Verify port 8080 is not in use

## Resources
https://mlflow.org/docs/latest/self-hosting/security/basic-http-auth/
https://mlflow.org/docs/latest/ml/
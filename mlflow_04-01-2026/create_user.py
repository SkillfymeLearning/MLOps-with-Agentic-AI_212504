from mlflow import MlflowClient
from mlflow.server import get_app_client
import os

tracking_uri = "http://localhost:8080/"
os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
os.environ["MLFLOW_TRACKING_USERNAME"] = "admin"
os.environ["MLFLOW_TRACKING_PASSWORD"] = "password@1234"
auth_client = get_app_client("basic-auth", tracking_uri=tracking_uri)
auth_client.create_user(username="user3", password="password3@1234")
auth_client.create_user(username="user4", password="password4@1234")

client = MlflowClient(tracking_uri=tracking_uri)
experiment_id = client.create_experiment(name="experiment4")

auth_client.create_experiment_permission(
    experiment_id=experiment_id, username="user4", permission="MANAGE"
)
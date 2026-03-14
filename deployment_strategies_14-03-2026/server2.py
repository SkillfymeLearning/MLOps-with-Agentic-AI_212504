import os
import boto3
import tensorflow as tf
import numpy as np
from urllib.parse import urlparse
import logging
from kserve import Model, ModelServer
from prometheus_client import Counter, Gauge  # Added Gauge

# Existing Counter
DIGIT_COUNTER = Counter('mnist_digit_predicted_total', 'Count of digits predicted', ['digit'])

# --- New Prometheus Metrics ---
# Accuracy: (Correct / Total)
MODEL_ACCURACY = Gauge('mnist_model_accuracy', 'Current accuracy of the model')
# Label Drift: (Frequency of Predicted 6s) - (Frequency of Actual 6s)
LABEL_DRIFT_6 = Gauge('mnist_label_drift_6', 'Label drift for digit 6')


# Internal state for calculation
metrics_state = {
    "total_count": 0,
    "correct_count": 0,
    "pred_6_count": 0,
    "actual_6_count": 0
}

# --- Random accuracy for testing ---
def set_random_accuracy():
    import random
    acc = random.uniform(0, 1)
    MODEL_ACCURACY.set(acc)
    logger.info(f"[TEST] Set random accuracy: {acc:.3f}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("MODEL_NAME", "mnist")
MODEL_DIR = "/app/model"
EXPORT_PATH = os.path.join(MODEL_DIR, "1")

# ... (Keeping get_s3_client and download_s3_folder exactly as they were) ...
def get_s3_client():
    endpoint = os.getenv("S3_ENDPOINT", "http://minio-service.kubeflow:9000")
    key = os.getenv("AWS_ACCESS_KEY_ID", "minio")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")
    logger.info(f"S3 endpoint: {endpoint}, key: {key}")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name="us-east-1",
    )

def download_s3_folder(s3_uri, local_dir):
    parsed = urlparse(s3_uri)
    bucket_name = parsed.netloc
    prefix = parsed.path.lstrip('/')
    s3 = boto3.client('s3',
        endpoint_url=os.getenv('S3_ENDPOINT', 'http://minio-service.kubeflow:9000'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name='us-east-1')
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get('Contents', []):
            rel_path = os.path.relpath(obj['Key'], prefix)
            target = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not obj['Key'].endswith('/'):
                s3.download_file(bucket_name, obj['Key'], target)

class MnistModel(Model):

    def __init__(self, name: str, model_version: str):
        super().__init__(name)
        self.name = name
        self.model_version = model_version
        self.model_layer = None
        self.ready = False

    def load(self) -> bool:
        model_uri = os.getenv(
            "TRAINED_MODEL_URI",
            "minio://mlpipeline/v2/artifacts/mnist-classifier-dev/489de8ab-4e8d-4937-9a60-bca7c5abf7d9/model-training/0a5c3414-acb6-4966-ac3a-502dd817eadc/model_trained/"
        )
        if not model_uri:
            raise RuntimeError("TRAINED_MODEL_URI environment variable is not set")
        logger.info(f"Downloading model from {model_uri}...")
        # download_s3_folder(model_uri, MODEL_DIR)
        logger.info(f"Loading SavedModel from {EXPORT_PATH}...")
        self.model_layer = tf.keras.layers.TFSMLayer(
            EXPORT_PATH, call_endpoint="serving_default"
        )
        logger.info("Model loaded ✅")
        self.ready = True
        return self.ready

    def predict(self, payload: dict, headers: dict = None) -> dict:
        try:
            instances = np.array(payload["instances"], dtype="float32")
            
            # Extract true label from payload for metric calculation
            # Your test script should now send: {"instances": [...], "true_label": 9}
            true_label = payload.get("true_label")

            if instances.ndim == 2:
                instances = np.expand_dims(instances, axis=0)
            if instances.max() > 1.0:
                instances = instances / 255.0
            instances = instances.reshape(-1, 28, 28, 1)

            predictions_dict = self.model_layer(instances)
            first_key = list(predictions_dict.keys())[0]
            result = predictions_dict[first_key].numpy().tolist()
            predicted_digit = int(np.argmax(result[0]))

            # 1. Update existing counter
            DIGIT_COUNTER.labels(digit=str(predicted_digit)).inc()

            # 2. Update Accuracy and Label Drift if true_label is provided
            if true_label is not None:
                true_label = int(true_label)
                metrics_state["total_count"] += 1
                
                if predicted_digit == true_label:
                    metrics_state["correct_count"] += 1
                
                if predicted_digit == 6:
                    metrics_state["pred_6_count"] += 1
                
                if true_label == 6:
                    metrics_state["actual_6_count"] += 1

                # Calculate and update Gauges
                acc = metrics_state["correct_count"] / metrics_state["total_count"]
                
                set_random_accuracy()  # For testing, comment this out in production
                # MODEL_ACCURACY.set(acc)

                drift = (metrics_state["pred_6_count"] / metrics_state["total_count"])
                LABEL_DRIFT_6.set(drift)

            return {"predictions": result}

        except Exception as e:
            logger.error(f"Inference error: {e}", exc_info=True)
            raise

if __name__ == "__main__":
    import sys
    model_version = sys.argv[1] if len(sys.argv) > 1 else "v1"

    model = MnistModel(MODEL_NAME, model_version=model_version)
    model.load()
    ModelServer(http_port=8686,).start([model])
import numpy as np
from tensorflow import keras
from kubernetes import client
import requests

# --- Option 1: Using KServe SDK to get endpoint, then requests (most common) ---


def test_model_with_mnist(image_index=0, use_local_port_forward=True):
    """
    Loads MNIST test data and sends a specific image to a KServe InferenceService.
    """
    # 1. Load the MNIST test dataset
    (_, _), (x_test, y_test) = keras.datasets.mnist.load_data()

    # 2. Select the image
    test_image = x_test[image_index]  # Shape: (28, 28)
    true_label = y_test[image_index]

    # 3. Build the endpoint URL
    name = "digits-server"
    namespace = "kubeflow"

    if use_local_port_forward:
        # When port-forwarding locally (kubectl port-forward)
        base_url = "http://127.0.0.1:8686"
        base_url = "http://127.0.0.1:8080"

    url = f"{base_url}/v1/models/mnist:predict"

    # 4. Build V1 payload (TensorFlow Serving format)
    # KServe v1 protocol: {"instances": [...]}
    payload = {
        "instances": test_image.tolist(),
        "true_label": int(true_label)  # list of shape [28, 28]
    }
    headers = {
    "Authorization": "Bearer YOUR_TOKEN",
    "Custom-Header": "value"
}

    try:
        print(f"Sending Image Index {image_index} (True Label: {true_label})...")
        # response = requests.post(url, json=payload, headers=headers, timeout=10)
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        # 5. Process the result
        predictions = response.json()["predictions"]
        predicted_class = np.argmax(predictions[0])

        print("-" * 30)
        print(f"PREDICTION: {predicted_class}")
        print(f"ACTUAL:     {true_label}")
        print("✅ MATCH!" if predicted_class == true_label else "❌ MISMATCH!")
        print("-" * 30)
        print(f"Confidence: {max(predictions[0]) * 100:.2f}%")

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        print("Tip: Ensure port-forward is active or you are running inside the cluster.")


# --- Option 2: KServe V2 Inference Protocol (gRPC or REST) ---
# If your InferenceService uses the Open Inference Protocol (v2), use this instead.

def test_model_v2(image_index=0):
    """
    Uses KServe's Open Inference Protocol v2 (REST) format.
    Switch to this if your ServingRuntime uses protocol: v2.http://127.0.0.1:8686/v1/models/digits-server
    """
    (_, _), (x_test, y_test) = keras.datasets.mnist.load_data()

    test_image = x_test[image_index].astype(np.float32)
    true_label = y_test[image_index]

    url = "http://127.0.0.1:8686/v2/models/mnist/infer"

    # V2 protocol payload format
    payload = {
        "inputs": [
            {
                "name": "input_1",           # Match the model's input tensor name
                "shape": [1, 28, 28],
                "datatype": "FP32",
                "data": test_image.tolist()
            }
        ]
    }

    try:
        print(f"[V2] Sending Image Index {image_index} (True Label: {true_label})...")
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        outputs = response.json()["outputs"]
        logits = outputs[0]["data"]
        predicted_class = int(np.argmax(logits))

        print("-" * 30)
        print(f"PREDICTION: {predicted_class}")
        print(f"ACTUAL:     {true_label}")
        print("✅ MATCH!" if predicted_class == true_label else "❌ MISMATCH!")
        print("-" * 30)

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")


# --- Run tests ---6 [100, 66,88, 123]
# images = [10, 42, 100, 120, 66, 72, 88, 123, 150, 200]
images = [100, 66, 88, 123, 250]  # Focus on these 6 number indices for testing
for i in images:
    test_model_with_mnist(image_index=i, use_local_port_forward=True)
    # test_model_v2(image_index=i)  # Uncomment to use V2 protocol
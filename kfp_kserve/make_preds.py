import numpy as np
import requests
from tensorflow import keras

def test_model_with_mnist(image_index=0):
    """
    Loads MNIST test data and sends a specific image to the serving endpoint.
    """
    # 1. Load the MNIST test dataset
    (_, _), (x_test, y_test) = keras.datasets.mnist.load_data()
    
    # 2. Select the image
    test_image = x_test[image_index] # Shape (28, 28)
    true_label = y_test[image_index]
    
    # 3. Endpoint setup
    # Note: This URL only works from WITHIN the Kubernetes cluster.
    name = "digits-server"
    namespace = "kubeflow"
    # url = f"http://{name}.{namespace}.svc.cluster.local:8501/v1/models/mnist:predict"
    url = "http://127.0.0.1:8501/v1/models/mnist:predict"

    # 4. Sending Request
    # We send the raw 28x28 list. The server handles reshaping/normalization.
    payload = {"instances": test_image.tolist()}
    
    try:
        print(f"Sending Image Index {image_index} (True Label: {true_label})...")
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        # 5. Process Result
        predictions = response.json()["predictions"]
        
        # Predictions will be a list of 10 probabilities (one for each digit)
        # argmax gets the index of the highest probability
        predicted_class = np.argmax(predictions[0]) 
        
        print("-" * 30)
        print(f"PREDICTION: {predicted_class}")
        print(f"ACTUAL:     {true_label}")
        print("✅ MATCH!" if predicted_class == true_label else "❌ MISMATCH!")
        print("-" * 30)
        print(f"Confidence: {max(predictions[0])*100:.2f}%")

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        print("Tip: Ensure you are running this from a Pod inside the same K8s cluster.")

# Test with a few different images
for i in [10, 42, 100]:
    test_model_with_mnist(image_index=i)
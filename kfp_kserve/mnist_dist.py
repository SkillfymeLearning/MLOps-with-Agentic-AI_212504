import inspect
import os
import kfp
from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model, Metrics, ClassificationMetrics
from kfp.client import Client
from kfp import compiler
import tf_script
# import kubernetes

@dsl.component(base_image="python:3.10-slim",
    packages_to_install=["numpy", "tensorflow"])
def load_dataset(x_train_artifact: Output[Dataset], x_test_artifact: Output[Dataset],y_train_artifact: Output[Dataset],y_test_artifact: Output[Dataset]):
    '''
    get dataset from Keras and load it separating input from output and train from test
    '''
    import numpy as np
    from tensorflow import keras
    import os
   
    (x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()
    
    import shutil
    np.save("/tmp/x_train.npy",x_train)
    shutil.move("/tmp/x_train.npy", x_train_artifact.path)

    np.save("/tmp/y_train.npy",y_train)
    shutil.move("/tmp/y_train.npy", y_train_artifact.path)

    np.save("/tmp/x_test.npy",x_test)
    shutil.move("/tmp/x_test.npy", x_test_artifact.path)

    np.save("/tmp/y_test.npy",y_test)
    shutil.move("/tmp/y_test.npy", y_test_artifact.path)

@dsl.component(
        base_image="python:3.10-slim",
        packages_to_install=["numpy"]
)
def preprocessing(metrics : Output[Metrics], x_train_processed : Output[Dataset], x_test_processed: Output[Dataset],
                  x_train_artifact: Input[Dataset], x_test_artifact: Input[Dataset]):
    ''' 
    just reshape and normalize data
    '''
    import numpy as np
    import os
    
    # load data artifact store
    x_train = np.load(x_train_artifact.path) 
    x_test = np.load(x_test_artifact.path)
    
    # reshaping the data
    # reshaping pixels in a 28x28px image with greyscale, canal = 1. This is needed for the Keras API
    x_train = x_train.reshape(-1,28,28,1)
    x_test = x_test.reshape(-1,28,28,1)
    # normalizing the data
    # each pixel has a value between 0-255. Here we divide by 255, to get values from 0-1
    x_train = x_train / 255
    x_test = x_test / 255
    
    #logging metrics using Kubeflow Artifacts
    metrics.log_metric("Len x_train", x_train.shape[0])
    metrics.log_metric("Len y_train", x_test.shape[0])
   
    
    # save feuture in artifact store
    import shutil
    np.save("tmp/x_train.npy",x_train)
    shutil.move("tmp/x_train.npy", x_train_processed.path)
    
    np.save("tmp/x_test.npy",x_test)
    shutil.move("tmp/x_test.npy", x_test_processed.path)

@dsl.component(base_image="python:3.10-slim",
    packages_to_install=["numpy", "tensorflow==2.15.1"])
def model_building(ml_model : Output[Model]):
    '''
    Define the model architecture
    This way it's more simple to change the model architecture and all the steps and indipendent
    '''
    from tensorflow import keras
    import tensorflow as tf
    import shutil
    import os
    
    #model definition
    model = keras.models.Sequential()
    model.add(keras.layers.Conv2D(64, (3, 3), activation='relu', input_shape=(28,28,1)))
    model.add(keras.layers.MaxPool2D(2, 2))

    model.add(keras.layers.Flatten())
    model.add(keras.layers.Dense(64, activation='relu'))
    model.add(keras.layers.Dense(32, activation='relu'))

    model.add(keras.layers.Dense(10, activation='softmax'))
    
    save_path = ml_model.path + ".keras"
    model.save(save_path)
    
    # Important: KFP expects the file at ml_model.path. 
    # Some environments require you to move it back to the exact path KFP expects
 
    shutil.move(save_path, ml_model.path)

@dsl.component(base_image="python:3.10-slim", packages_to_install=['numpy', 'tensorflow', 'scikit-learn', 'kubernetes', 'kfp', 'boto3'])
def model_training(
    train_code_string: str,
    ml_model : Input[Model],
    x_train_processed : Input[Dataset], x_test_processed: Input[Dataset],
    y_train_artifact : Input[Dataset], y_test_artifact :Input[Dataset],
    hyperparameters : dict, 
    metrics: Output[Metrics], 
    classification_metrics: Output[ClassificationMetrics], model_trained: Output[Model]
    ):
    """
    Build the model with Keras API
    Export model metrics
    """
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException
    import time, json, boto3, os
    from urllib.parse import urlparse
    import inspect
    import shutil

    # 1. Get the source code of your external script function
    # Note: mnist_dist_train_logic must be available in the local scope
    # or imported here.
    
    # Wrapper to trigger the function execution inside the container
    full_command = f"{train_code_string}\n\nmnist_dist_train_logic()"
    metrics_json_uri = f"{model_trained.uri}_metrics.json"
    # model_trained.uri = model_trained.uri + "/1/"
    # export_path = os.path.join(model_trained.path, "1")
    # os.makedirs(export_path, exist_ok=True)
    # model_trained.uri = export_path

    config.load_incluster_config()
    custom_api = client.CustomObjectsApi()
    
    tfjob_manifest = {
        "apiVersion": "kubeflow.org/v1",
        "kind": "TFJob",
        "metadata": {"name": "mnist-distributed", "namespace": "kubeflow"},
        "spec": {
            "tfReplicaSpecs": {
                "Worker": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "tensorflow",
                                "image": "python:3.10-slim",
                                "command": ["/bin/sh", "-c"],
                                "args": [f"pip install kubernetes tensorflow==2.15.1 boto3 numpy scikit-learn kfp && python3 -c \"{full_command}\""],
                                "env": [
                                    {"name": "X_TRAIN_URI", "value": str(x_train_processed.uri)},
                                    {"name": "Y_TRAIN_URI", "value": str(y_train_artifact.uri)},
                                    {"name": "X_TEST_URI", "value": str(x_test_processed.uri)},
                                    {"name": "Y_TEST_URI", "value": str(y_test_artifact.uri)},
                                    {"name": "LEARNING_RATE", "value": str(hyperparameters['lr'])},
                                    # Pass the URI of where to save the model
                                    {"name": "METRICS_JSON_URI", "value": metrics_json_uri},
                                    {"name": "MODEL_URI", "value": str(ml_model.uri)},
                                    {"name": "TRAINED_MODEL_URI", "value": str(model_trained.uri)},
                                    {"name": "TRAINED_MODEL_PATH", "value": str(model_trained.path)},
                                    {"name": "S3_ENDPOINT", "value": "http://minio-service.kubeflow:9000"},
                                    {"name": "AWS_ACCESS_KEY_ID", "value": "minio"},
                                    {"name": "AWS_SECRET_ACCESS_KEY", "value": "minio123"}
                                ]
                            }]
                        }
                    }
                }
            }
        }
    }

    tfjob_name = "mnist-distributed"
    namespace = "kubeflow"

    # 1. DELETE EXISTING JOB
    try:
        print(f"Deleting existing TFJob: {tfjob_name}")
        custom_api.delete_namespaced_custom_object(
            group="kubeflow.org",
            version="v1",
            namespace=namespace,
            plural="tfjobs",
            name=tfjob_name
        )
        # Give K8s a few seconds to clean up the resource and its pods
        print("Waiting for cleanup...")
        time.sleep(10) 
    except ApiException as e:
        if e.status == 404:
            print("No existing job found. Proceeding...")
        else:
            raise e

    # 2. CREATE THE NEW JOB
    print(f"Creating new TFJob: {tfjob_name}")
    custom_api.create_namespaced_custom_object(
        group="kubeflow.org",
        version="v1",
        namespace=namespace,
        plural="tfjobs",
        body=tfjob_manifest
    )

    # Polling logic to wait for 'Succeeded' status
    # while True:
    #     status = custom_api.get_namespaced_custom_object_status(
    #         "kubeflow.org", "v1", "kubeflow", "tfjobs", "mnist-dist-train"
    #     )
    #     if status.get("status", {}).get("state") == "Succeeded":
    #         break
    #     time.sleep(10)
    while True:
        job = custom_api.get_namespaced_custom_object("kubeflow.org", "v1", "kubeflow", "tfjobs", "mnist-distributed")
        status = job.get("status", {}).get("conditions", [])
        if any(c.get("type") == "Succeeded" for c in status): break
        if any(c.get("type") == "Failed" for c in status): raise Exception("TFJob Failed")
        time.sleep(20)

    # Final Step: Pull metrics back into KFP UI
    parsed = urlparse(metrics_json_uri)
    s3 = boto3.client('s3', endpoint_url="http://minio-service.kubeflow:9000", 
                    aws_access_key_id="minio", aws_secret_access_key="minio123")
    s3.download_file(parsed.netloc, parsed.path.lstrip('/'), 'meta.json')
    with open('meta.json', 'r') as f:
        meta = json.load(f)
        metrics.log_metric("accuracy", meta['metrics']['accuracy'])
        classification_metrics.log_confusion_matrix(['0','1','2','3','4','5','6','7','8','9'], meta['cmatrix'])
    shutil.copy("meta.json", metrics.path)
    shutil.copy("meta.json", classification_metrics.path)
    os.remove("meta.json")

@dsl.component(base_image="python:3.10", packages_to_install=['kubernetes'])
def model_serving(model_trained: Input[Model]):
    from kubernetes import client, config
    import os

    config.load_incluster_config()
    apps_v1 = client.AppsV1Api()
    core_v1 = client.CoreV1Api()
    
    namespace = "kubeflow"
    name = "digits-server"
    
    # We pass the URI into the container via an environment variable
    # to avoid complex string formatting in the shell command.
    model_uri = model_trained.uri

    serving_script = """
import os
import boto3
import tensorflow as tf
import numpy as np
from flask import Flask, request, jsonify
from urllib.parse import urlparse

app = Flask(__name__)

def download_s3_folder(s3_uri, local_dir):
    parsed = urlparse(s3_uri)
    bucket_name = parsed.netloc
    prefix = parsed.path.lstrip('/')
    
    # Use environment variables for credentials
    s3 = boto3.client('s3',
        endpoint_url=os.getenv('S3_ENDPOINT', 'http://minio-service.kubeflow:9000'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name='us-east-1')
    
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get('Contents', []):
            # Create local path
            rel_path = os.path.relpath(obj['Key'], prefix)
            target = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not obj['Key'].endswith('/'):
                s3.download_file(bucket_name, obj['Key'], target)

MODEL_DIR = '/tmp/model'
# Path to the exported SavedModel (the folder containing saved_model.pb)
export_path = os.path.join(MODEL_DIR, '1')

download_s3_folder(os.getenv('MODEL_URI'), MODEL_DIR)

# This is the Keras 3 way to handle the folder format you exported
model_layer = tf.keras.layers.TFSMLayer(export_path, call_endpoint='serving_default')

@app.route('/v1/models/mnist:predict', methods=['POST'])
def predict():
    try:
        data = request.json['instances']
        # Ensure input is float32 and normalized
        img = np.array(data).reshape(-1, 28, 28, 1).astype('float32') / 255.0
        
        # TFSMLayer returns a dictionary of outputs
        predictions_dict = model_layer(img)
        
        # Grab the first output key (usually 'output_0' or 'dense_2')
        first_key = list(predictions_dict.keys())[0]
        result = predictions_dict[first_key].numpy().tolist()
        
        return jsonify({'predictions': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

app.run(host='0.0.0.0', port=8501)
"""

    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [{
                        "name": "python-serving",
                        "image": "python:3.10-slim",
                        "env": [
                            {"name": "MODEL_URI", "value": model_uri},
                            {"name": "AWS_ACCESS_KEY_ID", "value": "minio"}, # Replace with actual or secretRef
                            {"name": "AWS_SECRET_ACCESS_KEY", "value": "minio123"},
                            {"name": "S3_ENDPOINT", "value": "http://minio-service.kubeflow:9000"}
                        ],
                        "command": ["/bin/sh", "-c"],
                        "args": [f"pip install flask tensorflow boto3 && python3 -c \"{serving_script}\""],
                        "ports": [{"containerPort": 8501}]
                    }]
                }
            }
        }
    }

    try:
        apps_v1.delete_namespaced_deployment(name=name, namespace=namespace)
    except: pass
    
    apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "selector": {"app": name}, # This MUST match the label in your deployment
            "ports": [
                {
                    "protocol": "TCP",
                    "port": 8501,       # The port other pods will call
                    "targetPort": 8501   # The port the container is listening on
                }
            ],
            "type": "ClusterIP" # Internal-only stable IP
        }
    }

    # Delete existing service if it exists to avoid 'AlreadyExists' error
    try:
        core_v1.delete_namespaced_service(name=name, namespace=namespace)
        print("Existing service deleted.")
    except:
        pass

    # Create the service
    core_v1.create_namespaced_service(namespace=namespace, body=service)
    print(f"Service {name} created in namespace {namespace}")

@dsl.pipeline(
    name='mnist-classifier-dev',
    description='Detect digits',
    # pipeline_root='s3://mlpipeline/v1/repositories/mnist/pipelines'
    )
def mnist_pipeline(hyperparameters: dict):
    load_task = load_dataset()
    local_script_text = inspect.getsource(tf_script.mnist_dist_train_logic)
    preprocess_task = preprocessing(
        x_train_artifact = load_task.outputs["x_train_artifact"],
        x_test_artifact = load_task.outputs["x_test_artifact"]
    )
    model_building_task = model_building()
    training_task = model_training(
        train_code_string=local_script_text,
        ml_model = model_building_task.outputs["ml_model"],
        x_train_processed = preprocess_task.outputs["x_train_processed"],
        x_test_processed = preprocess_task.outputs["x_test_processed"],
        y_train_artifact = load_task.outputs["y_train_artifact"],
        y_test_artifact = load_task.outputs["y_test_artifact"],
        hyperparameters = hyperparameters
    )
    serving_task = model_serving(model_trained = training_task.outputs["model_trained"])


hyperparameters ={"hyperparameters" :  {"lr":0.1, "num_epochs":1 } }
namespace="kubeflow"
compiler.Compiler().compile(mnist_pipeline, 'mnist_pipeline.yaml')
client = Client(host='http://localhost:8080')  # Replace with your endpoint
client.create_run_from_pipeline_func(mnist_pipeline, arguments=hyperparameters,experiment_name="test",namespace=namespace,enable_caching=True)
                                    #  pipeline_root='s3://mlpipeline/v1/repositories/mnist/pipelines')
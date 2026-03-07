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

    full_command = f"{train_code_string}\n\nmnist_dist_train_logic()"
    metrics_json_uri = f"{model_trained.uri}_metrics.json"

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

@dsl.component(base_image="python:3.10", packages_to_install=['kubernetes', 'kserve'])
def model_serving(model_trained: Input[Model]):
    """
    Create kserve instance
    """
    from kubernetes import client 
    from kserve import KServeClient
    from kserve import V1beta1InferenceService
    from kserve import V1beta1InferenceServiceSpec
    from kserve import V1beta1PredictorSpec
    from datetime import datetime
    import time

    namespace = "kubeflow"
    name = "digits-server"
    kind = "InferenceService"

    uri = model_trained.uri
    uri = uri.replace("minio", "s3")
    uri = uri.rsplit("/", 2)[0]

    api_version = 'serving.kserve.io/v1beta1'
    predictor = V1beta1PredictorSpec(
                service_account_name="sa-minio-kserve",
                containers=[
                    client.V1Container(
                        name="kserve-container",
                        image="mnist_tf:latest",
                        ports=[
                            client.V1ContainerPort(
                                container_port=8686,
                                protocol="TCP"
                            )
                        ],
                        env=[
                            client.V1EnvVar(name="STORAGE_URI", value=uri),
                            client.V1EnvVar(name="MODEL_NAME", value=name),
                        ],
                        resources=client.V1ResourceRequirements(
                            requests={"memory": "512Mi", "cpu": "500m"},
                            limits={"memory": "1Gi", "cpu": "1"}
                        ),
                        # KServe storage initializer will download model to /mnt/models
                        # Your server script must load from there
                        command=["python", "/app/server.py"]
                    )
                ]
            )
    isvc = V1beta1InferenceService(
        api_version=api_version,
        kind=kind,
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            annotations={
                'sidecar.istio.io/inject': 'false',
                'serving.kserve.io/deploymentMode': 'RawDeployment'
            }
        ),
        spec=V1beta1InferenceServiceSpec(
            predictor=predictor
        )
    )

    KServe = KServeClient()
    
    #replace old inference service with a new one
    from kubernetes.client.exceptions import ApiException

    def wait_for_deletion(kserve_client, name, namespace, timeout=120):
        start = time.time()
        while time.time() - start < timeout:
            try:
                kserve_client.get(name=name, namespace=namespace)
                print(f"Waiting for deletion of '{name}'...")
                time.sleep(5)
            except RuntimeError as e:
                if "404" in str(e) or "Not Found" in str(e):
                    print(f"'{name}' fully deleted.")
                    return True
                raise  # re-raise unexpected errors
        raise TimeoutError(f"ISVC '{name}' was not deleted within {timeout}s")

    # Delete if exists
    try:
        KServe.delete(name=name, namespace=namespace)
        print("Old ISVC delete request sent")
        wait_for_deletion(KServe, name, namespace)
    except RuntimeError as e:
        if "404" in str(e) or "Not Found" in str(e):
            print("No existing ISVC found, skipping delete")
        else:
            raise

    # Now safe to create
    try:
        KServe.create(isvc)
        print("InferenceService created successfully")
    except Exception as e:
        print("Create failed:", e)
        time.sleep(10)

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
import kfp
from kfp import Client, dsl
from typing import NamedTuple, List

# Step 1: Load data into memory and return as lists
@dsl.component(
    base_image="python:3.10-slim",
    packages_to_install=["pandas", "scikit-learn", "kfp"]
)
def load_data() -> NamedTuple("Outputs", [("features", List[List[float]]), ("labels", List[int])]):
    from sklearn.datasets import load_iris
    iris = load_iris()
    return (iris.data.tolist(), iris.target.tolist())

# Step 2: Train model and return accuracy
@dsl.component(
    base_image="python:3.10-slim",
    packages_to_install=["scikit-learn"]
)
def train_model(
    features: List[List[float]],
    labels: List[int]
) -> NamedTuple("Output", [("accuracy", float)]):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2)

    clf = RandomForestClassifier()
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    print(f"Model accuracy: {acc}")
    return (acc,)

# Step 3: Define the pipeline
@dsl.pipeline(
    name="iris-no-artifacts-pipeline",
    description="ML pipeline without file artifacts, returns accuracy."
)
def iris_pipeline():
    data = load_data()
    train_model(
        features=data.outputs["features"],
        labels=data.outputs["labels"]
    )

# Step 4: Compile
if __name__ == "__main__":
    kfp.compiler.Compiler().compile(
        pipeline_func=iris_pipeline,
        package_path="iris_pipeline.yaml"
    )
    #upload to Kubeflow 
    client = Client(host='http://localhost:8080')  # Replace with your endpoint
    client.upload_pipeline(pipeline_package_path='./iris_pipeline.yaml',pipeline_name="IRIS classifier",
                           namespace = 'kubeflow')
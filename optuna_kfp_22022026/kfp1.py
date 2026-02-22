from kfp import dsl
from kfp import compiler

# Define a simple component using a Python function
@dsl.component
def say_hello(name: str) -> str:
    """A simple component that says hello to a given name."""
    hello_text = f'Hello, {name}!'
    print(hello_text)
    return hello_text

# Define the pipeline using the @dsl.pipeline decorator
@dsl.pipeline(
    name="hello-world-pipeline",
    description="A basic pipeline that prints a greeting."
)
def hello_pipeline(recipient: str = "World") -> str:  # Add a default value
    """This pipeline runs the say_hello component."""
    hello_task = say_hello(name=recipient)
    return hello_task.output  # Return the output of the component

if __name__ == "__main__":
    # Compile the pipeline into a YAML file
    compiler.Compiler().compile(hello_pipeline, 'hello_world_pipeline.yaml')

    # To run the pipeline, you would typically use the Kubeflow Pipelines UI
    # or the KFP SDK Client if you have a running Kubeflow Pipelines backend:
    # from kfp.client import Client
    # client = Client(host='<YOUR-KFP-ENDPOINT>')  # Replace with your endpoint
    # run = client.create_run_from_pipeline_func(hello_pipeline, arguments={'recipient': 'Kubeflow'})
    # print(f"Pipeline run details: {run}")

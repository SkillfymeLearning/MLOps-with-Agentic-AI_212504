from kfp.client import Client

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
    return hello_task.output
client = Client(host='http://localhost:8080')  # Replace with your endpoint
run = client.create_run_from_pipeline_func(hello_pipeline, arguments={'recipient': 'Kubeflow'})
print(f"Pipeline run details: {run}")
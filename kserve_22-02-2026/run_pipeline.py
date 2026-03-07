import argparse
from kfp.client import Client
from kfp import compiler
import mnist_pipeline_file  # Assuming your pipeline code is in this file

def run(host, experiment, namespace, traffic, is_promotion):
    # 1. Prepare Arguments
    pipeline_args = {
        "hyperparameters": {"lr": 0.01, "num_epochs": 5},
        "canary_traffic_percent": int(traffic),
        "is_promotion": str(is_promotion).lower() == 'true'
    }

    # 2. Compile Pipeline
    pipeline_package_path = 'mnist_pipeline.yaml'
    compiler.Compiler().compile(
        pipeline_func=mnist_pipeline_file.mnist_pipeline,
        package_path=pipeline_package_path
    )

    # 3. Connect to KFP
    # In CI/CD, host is usually passed as an env var or secret
    client = Client(host=host)

    # 4. Trigger Run
    run_name = f"mnist_run_traffic_{traffic}"
    run_result = client.create_run_from_pipeline_package(
        pipeline_file=pipeline_package_path,
        arguments=pipeline_args,
        run_name=run_name,
        experiment_name=experiment,
        namespace=namespace
    )

    print(f"Run started: {run_result.run_id}")
    # Optional: Wait for completion if CI needs to fail on pipeline failure
    # run_result.wait_for_run_completion(timeout=1800)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8080")
    parser.add_argument("--experiment", default="mnist-traffic")
    parser.add_argument("--namespace", default="kubeflow")
    parser.add_argument("--traffic", default=10, type=int)
    parser.add_argument("--is_promotion", default=False, type=bool)
    
    args = parser.parse_args()
    run(args.host, args.experiment, args.namespace, args.traffic, args.is_promotion)

#python run_pipeline.py --traffic 10 --is_promotion False
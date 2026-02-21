from airflow.models import Variable

from airflow import DAG
from airflow.operators.docker_operator import DockerOperator
from datetime import datetime
from docker.types import Mount


# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2026, 2, 21),
    'retries': 1,
}

with DAG(
    dag_id='dvc_experiment_docker_dag',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
    description='Run DVC experiment and apply results using DockerOperator',
) as dag:
    exp_name = '{{ dag_run.conf["exp_name"] if dag_run and dag_run.conf.get("exp_name") else macros.datetime.now().strftime("%Y%m%d_%H%M%S") }}'

    dvc_exp_run = DockerOperator(
        task_id='dvc_exp_run',
        image='cicd-mlops-custom:latest',
        command=f'bash -c "dvc exp run --name {exp_name} --temp --pull && echo {exp_name} && dvc exp apply {exp_name} && dvc commit && dvc push"',
        working_dir='/workspace',
        auto_remove='never',
        do_xcom_push=True,
        force_pull=False,
        docker_url='unix://var/run/docker.sock',
        network_mode='mlflow-network',
        environment={
            'EXP_NAME': exp_name,
            'AWS_ACCESS_KEY_ID': Variable.get("AWS_ACCESS_KEY_ID"),
            'AWS_SECRET_ACCESS_KEY': Variable.get("AWS_SECRET_ACCESS_KEY"),
        }
    )
    

    # dvc_exp_apply = DockerOperator(
    #     task_id='dvc_exp_apply',
    #     image='cicd-mlops-custom:latest',
    #     command='bash -c "dvc exp apply $(cat /tmp/xcom_return)"',
    #     working_dir='/workspace',
    #     auto_remove='success',
    #     do_xcom_push=True,
    #     force_pull=False,
    #     docker_url='unix://var/run/docker.sock',
    #     environment={
    #         'AWS_ACCESS_KEY_ID': Variable.get("AWS_ACCESS_KEY_ID"),
    #         'AWS_SECRET_ACCESS_KEY': Variable.get("AWS_SECRET_ACCESS_KEY"),
    #     }
    # )

    dvc_exp_run

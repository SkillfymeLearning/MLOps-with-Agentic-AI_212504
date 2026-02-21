from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2026, 2, 21),
    'retries': 1,
}

with DAG(
    dag_id='dvc_experiment_dag',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:

    project_path = '/Users/ksarma/cicd-mlops'

    # 1. We generate the name inside the bash command and use 'echo' 
    # to send it to XCom (do_xcom_push=True)
    dvc_exp_run = BashOperator(
        task_id='dvc_exp_run',
        bash_command=(
            'EXP_NAME={{ dag_run.conf["exp_name"] if dag_run and dag_run.conf.get("exp_name") '
            'else macros.datetime.now().strftime("%Y%m%d_%H%M%S") }}; '
            f'dvc exp run -f --name $EXP_NAME --temp --pull && echo $EXP_NAME'
        ),
        cwd=project_path,
        do_xcom_push=True # This captures the 'echo $EXP_NAME' output
    )

    # 2. We pull that exact string from the previous task
    dvc_exp_apply = BashOperator(
        task_id='dvc_exp_apply',
        bash_command=(
            "EXP_NAME='{{ task_instance.xcom_pull(task_ids=\"dvc_exp_run\") }}'; "
            "dvc exp apply $EXP_NAME"
        ),
        cwd=project_path
    )

    dvc_exp_run >> dvc_exp_apply
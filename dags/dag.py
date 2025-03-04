from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

# Definição da DAG
with DAG(
    dag_id="my_first_fucking_dag_bro",
    schedule_interval="@daily",  # Roda diariamente
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["teste", "aprendizado"],
) as dag:

    # Task que executa um comando Bash
    tarefa1 = BashOperator(
        task_id="exibir_mensagem",
        bash_command='echo "Minha primeira DAG no Airflow!"',
    )
    tarefa2 = BashOperator(
        task_id="exibir_mensagem2",
        bash_command='echo "Minha 2 DAG no Airflow!"',
    )
    tarefa3 = BashOperator(
        task_id="exibir_mensagem3porra",
        bash_command='echo "Minha 2 DAG no Airflow!"',
    )

    # Executando a DAG
    tarefa1,tarefa2,tarefa3

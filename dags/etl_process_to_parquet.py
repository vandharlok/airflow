from airflow import DAG
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.python import PythonOperator
from datetime import datetime
import pandas as pd
import os

# Caminho para salvar o arquivo Parquet
PARQUET_FILE_PATH = "/opt/airflow/dags/output/data.parquet"


def extract_data():
    try:
        print("🔍 Tentando se conectar ao PostgreSQL...")
        postgres_hook = PostgresHook(postgres_conn_id="postgres_default")
        conn = postgres_hook.get_conn()

        print("✅ Conexão com o PostgreSQL estabelecida com sucesso!")

        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()
            if result:
                print("✅ Teste de conexão bem-sucedido! PostgreSQL respondeu corretamente.")

        print("📦 Executando query para extrair os dados...")
        df = pd.read_sql_query("SELECT * FROM produtos", conn)

        print(f"✅ {len(df)} registros extraídos da tabela `produtos`.")

        # Caminho do arquivo
        raw_csv_path = "/opt/airflow/dags/output/raw_data.csv"

        # 🔹 Criar o diretório se ele não existir
        os.makedirs(os.path.dirname(raw_csv_path), exist_ok=True)

        # Salvar o CSV
        df.to_csv(raw_csv_path, index=False)
        print(f"📁 Dados salvos para referência em {raw_csv_path}")

        return df.to_json()

    except Exception as e:
        print(f"❌ Erro na extração dos dados: {str(e)}")
        raise

# Função para transformar dados
def transform_data(ti):
    try:
        raw_json = ti.xcom_pull(task_ids='extract_task')
        df = pd.read_json(raw_json)

        # Exemplo de transformação: Remover NaN e normalizar estoque
        df["estoque_atual"] = df["estoque_atual"].fillna(0)  # Substitui NaN por 0
        df = df.drop_duplicates()  # Remove duplicatas

        processed_csv_path = "/opt/airflow/dags/output/processed_data.csv"
        os.makedirs(os.path.dirname(processed_csv_path), exist_ok=True)
        df.to_csv(processed_csv_path, index=False)

        print(f"✅ Dados transformados e salvos em {processed_csv_path}")
        return df.to_json()

    except Exception as e:
        print(f"❌ Erro na transformação dos dados: {str(e)}")
        raise

# Função para salvar os dados em Parquet
def load_data(ti):
    try:
        transformed_json = ti.xcom_pull(task_ids='transform_task')
        df = pd.read_json(transformed_json)

        os.makedirs(os.path.dirname(PARQUET_FILE_PATH), exist_ok=True)
        df.to_parquet(PARQUET_FILE_PATH, index=False)

        print(f"✅ Dados carregados com sucesso em {PARQUET_FILE_PATH}")

    except Exception as e:
        print(f"❌ Erro ao salvar os dados em Parquet: {str(e)}")
        raise

# Definição da DAG
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 2, 27),
    'retries': 1
}

dag = DAG(
    'etl_postgres_to_parquet',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False
)

extract_task = PythonOperator(
    task_id='extract_task',
    python_callable=extract_data,
    dag=dag
)

transform_task = PythonOperator(
    task_id='transform_task',
    python_callable=transform_data,
    dag=dag
)

load_task = PythonOperator(
    task_id='load_task',
    python_callable=load_data,
    dag=dag
)

# Definição da ordem das tasks
extract_task >> transform_task >> load_task

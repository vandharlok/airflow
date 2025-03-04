from airflow import DAG
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.python import PythonOperator
from datetime import datetime,timedelta,timezone
import pandas as pd
import os
import requests
import pandas as pd
import os
from dotenv import load_dotenv


# Caminho para salvar o arquivo Parquet
PARQUET_FILE_PATH = "/opt/airflow/dags/output/data.parquet"
load_dotenv()
api_token=os.getenv("TOKEN")

class HomeAssistantAPI:
    def __init__(self, host="192.168.1.110:8123", token=None):
        self.host = host
        self.base_url = f"http://{host}/api/"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_entity_history(self, entity_id, start_time=None, end_time=None, days=1000, block_days=30):
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        elif isinstance(end_time, str):
            end_time = pd.to_datetime(end_time).tz_localize("UTC")

        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(days=days)
        elif isinstance(start_time, str):
            start_time = pd.to_datetime(start_time).tz_localize("UTC")

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        full_history = []
        current_end_time = end_time
        delta = timedelta(days=block_days)

        while current_end_time > start_time:
            block_start_time = max(start_time, current_end_time - delta)
            block_start_iso = block_start_time.isoformat(timespec="microseconds")
            current_end_iso = current_end_time.isoformat(timespec="microseconds")

            url = f"{self.base_url}history/period/{block_start_iso}"
            params = {
                "end_time": current_end_iso,
                "filter_entity_id": entity_id
            }

            df = self._fetch_data(url, params=params)
            if df is not None and not df.empty:
                full_history.append(df)

            current_end_time = block_start_time - timedelta(microseconds=1)

        if full_history:
            df_final = pd.concat(full_history).drop_duplicates().sort_values("last_changed")
            return df_final
        else:
            print(f"⚠️ Nenhum dado histórico encontrado para {entity_id}")
            return None

    def _fetch_data(self, url, params=None):
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            print(response.raise_for_status())

            history_data = response.json()

            if not history_data or len(history_data) == 0 or not history_data[0]:
                print("⚠️ Nenhum dado retornado.")
                return None
            ##erro ta aki 
            df = pd.DataFrame(history_data[0])
            if "last_changed" not in df.columns or "state" not in df.columns:
                print("⚠️ Dados sem colunas esperadas.")
                return None

            df = df[["last_changed", "state"]]
            df["last_changed"] = pd.to_datetime(df["last_changed"], utc=True)
            df["state"] = pd.to_numeric(df["state"], errors="coerce")

            return df
        except requests.exceptions.RequestException as e:
            print(f"❌ Erro de conexão: {str(e)}")
            return None

    def get_states(self, debug=True):
            """Get all entity states"""
            response = requests.get(f"{self.base_url}states", headers=self.headers)
            
            if debug:
                print("Request URL:", response.url)
                print("Response Status Code:", response.status_code)
                print("Response Headers:", response.headers)
                print("Response Text:", response.text[:500])  # First 500 characters
                
            if response.status_code != 200:
                raise Exception(f"Error {response.status_code}: {response.text}")
                
            try:
                return response.json()
            except requests.exceptions.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                print("Full Response Text:", response.text)
                raise
            
# Função de extração para o Airflow DAG
def extract_data():
    try:
        print("🔍 Tentando se conectar ao Home Assistant...")
        TOKEN = api_token
        if not TOKEN:
            raise ValueError("❌ Token de autenticação não encontrado.")

        ha = HomeAssistantAPI(token=TOKEN)
        print("\nTesting API connection...")
        states = ha.get_states()

        print(ha)
        all_states = ha.get_states()
        for entity in all_states:
            print(f"{entity['entity_id']}: {entity['state']}")

        entity_consumo_mes = "sensor.abc_consumo_ativo_total"
        print(f"📦 Extraindo histórico da entidade {entity_consumo_mes}...")
        history = ha.get_entity_history(entity_consumo_mes)
        print(history)

        if history is None or history.empty:
            raise ValueError(f"❌ Nenhum dado encontrado para {entity_consumo_mes}")

        history = history.dropna()
        print(f"✅ {len(history)} registros extraídos.")

        raw_csv_path = "/tmp/raw_data_2.csv"
        os.makedirs(os.path.dirname(raw_csv_path), exist_ok=True)
        history.to_csv(raw_csv_path, index=False)
        print(f"📁 Dados salvos em {raw_csv_path}")

        # Option 1: Reset index before converting to JSON
        history = history.reset_index(drop=True)
        return history.to_json()

        # Option 2: Alternatively, use a different orient that does not require unique index
        # return history.to_json(orient="records")

    except Exception as e:
        print(f"❌ Erro na extração dos dados: {str(e)}")
        raise

# Função para transformar dados
def transform_data(ti):
    try:
        raw_json = ti.xcom_pull(task_ids='extract_task')
        df = pd.read_json(raw_json)

        # Exemplo de transformação: Remover NaN e normalizar estoque
        df["state"] = df["state"].fillna(0)  # Substitui NaN por 0
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

        # ✅ Correção: Converter timestamp para datetime UTC
        if "last_changed" in df.columns:
            df["last_changed"] = pd.to_datetime(df["last_changed"], unit="ms", utc=True)

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
    'ha_etl_process',
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

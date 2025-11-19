# dags/Alerts_DAG.py
"""
DAG pour les alertes proactives aux chauffeurs.
S'exécute toutes les 10 minutes.
Utilise une approche proactive: prédit la route des chauffeurs et les alerte AVANT qu'ils n'atteignent une congestion.
"""

from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/opt/airflow')

default_args = {
    'owner': 'congestion_team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
    'email_on_failure': False,
    'email_on_retry': False,
}

def send_alerts_task(**context):
    """
    Analyse les congestions et envoie des alertes WhatsApp anticipées aux chauffeurs.
    Cette tâche prédit la route des chauffeurs et les alerte AVANT qu'ils n'atteignent une congestion.
    """
    try:
        # Import lazy pour éviter le timeout au chargement du DAG
        from src.alert import run_alerts
        
        result = run_alerts()
        print(f"Résultat des alertes proactives: {result}")
        return result
    except Exception as e:
        print(f"Erreur lors de l'envoi des alertes: {e}")
        import traceback
        traceback.print_exc()
        return {"alerts_envoyées": 0, "erreurs": 1, "statut": "erreur", "message": str(e)}

with DAG(
    'proactive_alerts',
    default_args=default_args,
    description='Alertes proactives aux chauffeurs - Prédiction de route et alertes anticipées',
    schedule_interval='*/10 * * * *',  # Exécution toutes les 10 minutes
    catchup=False,
    tags=['alerts', 'proactive', 'drivers']
) as dag:

    send_alerts = PythonOperator(
        task_id='send_proactive_alerts',
        python_callable=send_alerts_task,
        execution_timeout=timedelta(minutes=10),
        retries=1,
    )

    send_alerts


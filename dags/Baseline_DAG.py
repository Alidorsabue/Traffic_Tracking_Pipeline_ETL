# dags/Baseline_DAG.py
"""
DAG pour calculer la baseline horaire de vitesse par tronçon.
S'exécute une fois par jour à 2h du matin (période de faible trafic).
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
    'retries': 2,
    'retry_delay': timedelta(minutes=15),
    'email_on_failure': False,
    'email_on_retry': False,
}

def compute_baseline_task(**context):
    """
    Calcule la baseline horaire de vitesse pour chaque tronçon.
    Utilise automatiquement tous les jours disponibles dans edge_agg.
    Si moins de 30 jours sont disponibles, utilise tous les jours disponibles.
    Sauvegarde le résultat dans la table edge_hourly_baseline.
    """
    try:
        # Import lazy pour éviter le timeout au chargement du DAG
        from src.baseline import compute_hourly_baseline
        
        print("Début du calcul de la baseline horaire...")
        print("   Détection automatique des jours disponibles...")
        
        # Calculer la baseline avec détection automatique des jours disponibles
        # history_days=None permet la détection automatique
        # min_days=1 permet de calculer même avec seulement 1 jour de données
        baseline = compute_hourly_baseline(history_days=None, min_days=1)
        
        if baseline is not None and not baseline.empty:
            print(f"Baseline calculée avec succès: {len(baseline)} lignes")
            print(f"   Couverture: {baseline['edge_u'].nunique()} tronçons uniques")
            print(f"   Heures couvertes: {sorted(baseline['hour'].unique())}")
            return "success"
        else:
            print("Échec du calcul de la baseline ou baseline vide")
            print("   Vérifier que la table edge_agg contient des données")
            print("   La baseline nécessite au moins 1 jour de données dans edge_agg")
            return "failed"
            
    except Exception as e:
        print(f"Erreur lors du calcul de la baseline: {e}")
        import traceback
        traceback.print_exc()
        return "error"

with DAG(
    'compute_baseline_daily',
    default_args=default_args,
    description='Calcule la baseline horaire de vitesse par tronçon une fois par jour',
    schedule_interval='0 2 * * *',  # Tous les jours à 2h du matin
    catchup=False,
    tags=['baseline', 'maintenance', 'daily']
) as dag:

    compute_baseline = PythonOperator(
        task_id='compute_baseline',
        python_callable=compute_baseline_task,
        execution_timeout=timedelta(minutes=45),  # Timeout de 45 minutes
    )

    compute_baseline


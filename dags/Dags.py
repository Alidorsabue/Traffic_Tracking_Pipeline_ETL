from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta
import sys
import pandas as pd
sys.path.insert(0, '/opt/airflow')

from src.Script_ETL import (
    extract_recent_data, clean_data, detect_congestion, 
    aggregate_by_zone, load_to_db, aggregate_by_edge, load_edge_agg_to_db, load_predictions_to_db
)
# Note: Les imports de mapmatching et model sont déplacés dans les fonctions pour éviter
# les timeouts lors du chargement du DAG (osmnx est très lourd à importer)

default_args = {
    'owner': 'congestion_team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'email_on_failure': False,
    'email_on_retry': False,
}

# Args spécifiques pour mapmatching (tâche longue et coûteuse)
mapmatching_args = {
    'owner': 'congestion_team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 2,  # Plus de retries pour mapmatching
    'retry_delay': timedelta(minutes=10),
    'execution_timeout': timedelta(minutes=15),  # Timeout de 15 minutes
    'email_on_failure': False,
    'email_on_retry': False,
}

def extract_task(**context):
    """Extrait les données GPS récentes de la base de données."""
    df = extract_recent_data()
    return df

def clean_task(**context):
    """Nettoie les données GPS (suppression des doublons, filtrage des vitesses aberrantes)."""
    ti = context['ti']
    df = ti.xcom_pull(task_ids='extract_data')
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df, pd.DataFrame):
        df_clean = clean_data(df)
        return df_clean
    return pd.DataFrame()

def mapmatching_task(**context):
    """
    Associe les points GPS aux tronçons de route (map matching).
    Gestion d'erreur robuste pour éviter de bloquer le pipeline.
    """
    try:
        # Import lazy pour éviter le timeout au chargement du DAG
        from src.mapmatching import effectuer_mapmatching
        
        ti = context['ti']
        df_clean = ti.xcom_pull(task_ids='clean_data')
        if df_clean is None or df_clean.empty:
            print("Aucune donnée à traiter pour mapmatching")
            return pd.DataFrame()
        if isinstance(df_clean, pd.DataFrame):
            # OPTIMISATION: Réduire drastiquement max_points pour éviter les timeouts
            # 30 points au lieu de 50 pour réduire encore plus le temps d'exécution
            print(f"Début mapmatching sur {len(df_clean)} points (limité à 30)")
            df_matched = effectuer_mapmatching(df_clean, max_points=30, max_distance=50)
            matched_count = df_matched['edge_u'].notna().sum() if 'edge_u' in df_matched.columns else 0
            print(f"Mapmatching terminé: {matched_count}/{len(df_matched)} points matchés")
            return df_matched
        return pd.DataFrame()
    except Exception as e:
        print(f"Erreur dans mapmatching: {e}")
        import traceback
        traceback.print_exc()
        # Retourner un DataFrame vide plutôt que de faire échouer la tâche
        # Cela permet aux autres branches du pipeline de continuer
        return pd.DataFrame()

def detect_congestion_task(**context):
    """Détecte les embouteillages basés sur la vitesse et l'heure."""
    ti = context['ti']
    df_clean = ti.xcom_pull(task_ids='clean_data')
    if df_clean is None or (isinstance(df_clean, pd.DataFrame) and df_clean.empty):
        return pd.DataFrame()
    df_congestion = detect_congestion(df_clean)
    return df_congestion

def aggregate_by_zone_task(**context):
    """Agrège les données de congestion par zones géographiques."""
    ti = context['ti']
    df_congestion = ti.xcom_pull(task_ids='detect_congestion')
    if df_congestion is None or (isinstance(df_congestion, pd.DataFrame) and df_congestion.empty):
        return pd.DataFrame()
    df_aggregated = aggregate_by_zone(df_congestion)
    return df_aggregated

def load_congestion_task(**context):
    """Charge les données agrégées de congestion dans la table congestion."""
    ti = context['ti']
    df_aggregated = ti.xcom_pull(task_ids='aggregate_data')
    
    if df_aggregated is None:
        print("load_congestion_task: Aucune donnée XCom reçue de aggregate_data")
        return "no_data"
    
    if isinstance(df_aggregated, pd.DataFrame) and df_aggregated.empty:
        print("load_congestion_task: DataFrame congestion vide, aucune donnée à charger")
        return "empty_data"
    
    if not isinstance(df_aggregated, pd.DataFrame):
        print(f"load_congestion_task: Type de données inattendu: {type(df_aggregated)}")
        return "invalid_data"
    
    # Charger les données
    success = load_to_db(df_aggregated)
    
    if success:
        print(f"load_congestion_task: Succès - {len(df_aggregated)} lignes chargées")
        return "success"
    else:
        print(f"load_congestion_task: Échec du chargement")
        return "error"

def aggregate_by_edge_task(**context):
    """
    Agrège les données GPS par tronçon de route (edge) pour l'analyse prédictive.
    Continue même si mapmatching a échoué (retourne DataFrame vide).
    """
    try:
        ti = context['ti']
        df_matched = ti.xcom_pull(task_ids='mapmatching')
        
        if df_matched is None:
            print("Aucune donnée matchée disponible pour l'agrégation par edge (XCom None)")
            return pd.DataFrame()
        
        if isinstance(df_matched, pd.DataFrame) and df_matched.empty:
            print("DataFrame matché vide, pas d'agrégation par edge possible")
            return pd.DataFrame()
        
        if isinstance(df_matched, pd.DataFrame):
            # Vérifier que les colonnes nécessaires sont présentes
            required_cols = ['edge_u', 'edge_v', 'speed', 'timestamp']
            missing_cols = set(required_cols) - set(df_matched.columns)
            if missing_cols:
                print(f"Colonnes manquantes pour l'agrégation par edge: {missing_cols}")
                return pd.DataFrame()
            
            df_edge_agg = aggregate_by_edge(df_matched, time_interval_minutes=10)
            if df_edge_agg is not None and not df_edge_agg.empty:
                print(f"Agrégation par edge terminée: {len(df_edge_agg)} tronçons agrégés")
            else:
                print("Résultat de l'agrégation par edge vide")
            return df_edge_agg if df_edge_agg is not None else pd.DataFrame()
        
        print(f"Type de données inattendu pour mapmatching: {type(df_matched)}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Erreur lors de l'agrégation par edge: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def load_edge_agg_task(**context):
    """Charge les données agrégées par edge dans la table edge_agg."""
    ti = context['ti']
    df_edge_agg = ti.xcom_pull(task_ids='aggregate_edge')
    
    if df_edge_agg is None:
        print("load_edge_agg_task: Aucune donnée XCom reçue de aggregate_edge")
        return "no_data"
    
    if isinstance(df_edge_agg, pd.DataFrame) and df_edge_agg.empty:
        print("load_edge_agg_task: DataFrame edge_agg vide, aucune donnée à charger")
        return "empty_data"
    
    if not isinstance(df_edge_agg, pd.DataFrame):
        print(f"load_edge_agg_task: Type de données inattendu: {type(df_edge_agg)}")
        return "invalid_data"
    
    # Charger les données
    success = load_edge_agg_to_db(df_edge_agg)
    
    if success:
        print(f"load_edge_agg_task: Succès - {len(df_edge_agg)} lignes chargées")
        return "success"
    else:
        print(f"load_edge_agg_task: Échec du chargement")
        return "error"

def train_model_task(**context):
    """
    Entraîne le modèle Random Forest pour prédire la vitesse future.
    Cette tâche peut être exécutée moins fréquemment (ex: une fois par jour).
    """
    # Import lazy pour éviter le timeout au chargement du DAG
    from src.model import train_model
    
    model = train_model()
    if model is not None:
        print("Modèle entraîné avec succès")
        return "success"
    else:
        print("Échec de l'entraînement du modèle")
        return "failed"

def predict_task(**context):
    """
    Prédit la vitesse future pour les tronçons récents.
    Utilise le modèle pré-entraîné pour générer des prédictions.
    """
    try:
        # Import lazy pour éviter le timeout au chargement du DAG
        from src.model import predict_next
        
        df_predictions = predict_next()
        if df_predictions is None or (isinstance(df_predictions, pd.DataFrame) and df_predictions.empty):
            print("Aucune prédiction générée")
            return pd.DataFrame()
        print(f"Prédictions générées: {len(df_predictions)} lignes")
        return df_predictions
    except Exception as e:
        print(f"Erreur lors de la génération des prédictions: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def load_predictions_task(**context):
    """Charge les prédictions dans la table predictions."""
    ti = context['ti']
    df_predictions = ti.xcom_pull(task_ids='predict')
    
    if df_predictions is None:
        print("load_predictions_task: Aucune donnée XCom reçue de predict")
        return "no_data"
    
    if isinstance(df_predictions, pd.DataFrame) and df_predictions.empty:
        print("load_predictions_task: DataFrame predictions vide, aucune prédiction à charger")
        return "empty_data"
    
    if not isinstance(df_predictions, pd.DataFrame):
        print(f"load_predictions_task: Type de données inattendu: {type(df_predictions)}")
        return "invalid_data"
    
    # Charger les prédictions
    success = load_predictions_to_db(df_predictions)
    
    if success:
        print(f"load_predictions_task: Succès - {len(df_predictions)} prédictions chargées")
        return "success"
    else:
        print(f"load_predictions_task: Échec du chargement")
        return "error"

def send_alerts_task(**context):
    """
    Analyse les congestions et envoie des alertes WhatsApp aux chauffeurs concernés.
    Cette tâche s'exécute après le chargement des données edge_agg pour avoir les dernières données.
    """
    # Import lazy pour éviter le timeout au chargement du DAG
    from src.alert import run_alerts
    
    result = run_alerts()
    print(f"Résultat des alertes: {result}")
    return result

with DAG(
    'congestion_etl_modular',
    default_args=default_args,
    description='Pipeline ETL pour la détection de congestion et l\'analyse prédictive du trafic',
    schedule_interval='*/10 * * * *',  # Exécution toutes les 10 minutes
    catchup=False,
    tags=['congestion', 'traffic', 'prediction']
) as dag:

    # Tâche d'extraction
    extract = PythonOperator(
        task_id='extract_data',
        python_callable=extract_task,
    )

    # Tâche de nettoyage
    clean = PythonOperator(
        task_id='clean_data',
        python_callable=clean_task,
    )

    # Tâche de map matching (avec timeout et retries augmentés)
    mapmatching = PythonOperator(
        task_id='mapmatching',
        python_callable=mapmatching_task,
        **mapmatching_args,
    )

    # Branche 1: Détection de congestion (basée sur les données nettoyées)
    detect = PythonOperator(
        task_id='detect_congestion',
        python_callable=detect_congestion_task,
    )

    aggregate_zone = PythonOperator(
        task_id='aggregate_data',
        python_callable=aggregate_by_zone_task,
    )

    load_congestion = PythonOperator(
        task_id='load_data',
        python_callable=load_congestion_task,
    )

    # Branche 2: Agrégation par edge pour la prédiction (basée sur les données avec map matching)
    aggregate_edge = PythonOperator(
        task_id='aggregate_edge',
        python_callable=aggregate_by_edge_task,
    )

    load_edge_agg = PythonOperator(
        task_id='load_edge_agg',
        python_callable=load_edge_agg_task,
    )

    # Branche 3: Machine Learning - Entraînement et Prédiction
    train_ml = PythonOperator(
        task_id='train_model',
        python_callable=train_model_task,
    )

    predict = PythonOperator(
        task_id='predict',
        python_callable=predict_task,
    )

    load_predictions = PythonOperator(
        task_id='load_predictions',
        python_callable=load_predictions_task,
    )

    # Branche 4: Alertes aux chauffeurs (s'exécute après le chargement des données edge_agg ET load_congestion)
    send_alerts = PythonOperator(
        task_id='send_alerts',
        python_callable=send_alerts_task,
        execution_timeout=timedelta(minutes=10),  # Timeout de 10 minutes pour l'envoi des alertes
        retries=1,  # Retry en cas d'échec temporaire
    )

    # Définir l'ordre d'exécution des tâches
    # Flux principal: extract -> clean -> mapmatching
    # Puis deux branches parallèles:
    #   - Branche 1: detect -> aggregate_zone -> load_congestion (données nettoyées) - INDÉPENDANTE
    #   - Branche 2: aggregate_edge -> load_edge_agg (données avec map matching) - OPTIONNELLE
    #   - Branche 3: train_model -> predict -> load_predictions (ML - exécutée après edge_agg) - OPTIONNELLE
    
    extract >> clean >> [mapmatching, detect]
    
    # Branche congestion (INDÉPENDANTE - continue même si mapmatching échoue)
    detect >> aggregate_zone >> load_congestion
    
    # Branche edge aggregation puis ML (OPTIONNELLE - utilise trigger_rule='all_done')
    # Cela permet de continuer même si mapmatching échoue ou retourne des données vides
    mapmatching >> aggregate_edge >> load_edge_agg >> train_ml >> predict >> load_predictions
    
    # Branche alertes (s'exécute après le chargement des données edge_agg ET load_congestion)
    # Utilise trigger_rule pour s'exécuter même si l'une des tâches échoue
    [load_edge_agg, load_congestion] >> send_alerts
    
    # Rendre les tâches dépendantes de mapmatching plus tolérantes
    # 'all_done' permet l'exécution même si les tâches précédentes ont échoué ou été ignorées
    aggregate_edge.trigger_rule = 'all_done'
    load_edge_agg.trigger_rule = 'all_done'
    train_ml.trigger_rule = 'all_done'
    predict.trigger_rule = 'all_done'
    load_predictions.trigger_rule = 'all_done'
    send_alerts.trigger_rule = 'all_done'
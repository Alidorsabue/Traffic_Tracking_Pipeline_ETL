from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta
import sys
import pandas as pd
sys.path.insert(0, '/opt/airflow')

from src.Script_ETL import (
    extract_recent_data, clean_data, detect_congestion, 
    aggregate_by_zone, load_to_db, aggregate_by_edge, load_edge_agg_to_db, load_predictions_to_db,
    load_mapmatching_from_cache
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

# Args spécifiques pour mapmatching (maintenant rapide car utilise le cache)
# OPTIMISATION: Plus besoin de timeout strict car on charge depuis la base de données
mapmatching_args = {
    'owner': 'congestion_team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
    'execution_timeout': timedelta(minutes=2),  # Timeout court car c'est juste une lecture DB
    'email_on_failure': False,
    'email_on_retry': False,
}

def extract_task(**context):
    """Extrait les données GPS récentes de la base de données."""
    try:
        print("🔍 Extraction des données GPS récentes...")
        df = extract_recent_data()
        
        if df is None:
            print("❌ ERREUR: extract_recent_data() a retourné None")
            return pd.DataFrame()
        
        if isinstance(df, pd.DataFrame):
            if df.empty:
                print("⚠️ ATTENTION: Aucune donnée GPS trouvée dans la table gps_points")
                print("   Vérifier que l'app mobile envoie des données à la base de données")
                return pd.DataFrame()
            else:
                print(f"✅ {len(df)} lignes GPS extraites")
                print(f"   Période: {df['timestamp'].min()} à {df['timestamp'].max()}")
                return df
        else:
            print(f"❌ ERREUR: extract_recent_data() a retourné un type inattendu: {type(df)}")
            return pd.DataFrame()
    except Exception as e:
        print(f"❌ ERREUR lors de l'extraction: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

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
    Charge les résultats de map matching depuis le cache (mapmatching_cache).
    OPTIMISATION: Utilise le cache au lieu d'exécuter mapmatching à chaque fois.
    Le map matching est effectué une fois par heure par le DAG mapmatching_cache_hourly.
    Cette tâche est maintenant ultra-rapide car elle charge simplement depuis la base de données.
    """
    try:
        print("📦 Chargement des résultats de map matching depuis le cache...")
        
        # Charger depuis le cache (dernière heure)
        df_matched = load_mapmatching_from_cache(hours_back=1)
        
        if df_matched.empty:
            print("⚠️ Aucune donnée dans le cache mapmatching. Le DAG mapmatching_cache_hourly doit s'exécuter pour remplir le cache.")
            print("   Note: Le pipeline continuera mais sans données matchées pour l'agrégation par edge.")
            return pd.DataFrame()
        
        # Vérifier que les colonnes nécessaires sont présentes
        required_cols = ['edge_u', 'edge_v', 'speed', 'timestamp']
        missing_cols = set(required_cols) - set(df_matched.columns)
        if missing_cols:
            print(f"⚠️ Colonnes manquantes dans le cache: {missing_cols}")
            return pd.DataFrame()
        
        # Compter les points matchés
        matched_count = df_matched['edge_u'].notna().sum() if 'edge_u' in df_matched.columns else 0
        print(f"✅ {len(df_matched)} points chargés depuis le cache: {matched_count} matchés ({matched_count/len(df_matched)*100:.1f}%)")
        
        return df_matched
        
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement depuis le cache: {e}")
        import traceback
        traceback.print_exc()
        # Retourner un DataFrame vide plutôt que de faire échouer la tâche
        # Cela permet aux autres branches du pipeline de continuer
        # Les tâches suivantes avec trigger_rule='all_done' s'exécuteront quand même
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

# DAG 1: Détection de congestion rapide (toutes les 10 minutes) - SANS mapmatching
# Ce DAG est léger et rapide, utilise uniquement les coordonnées GPS brutes

with DAG(
    'congestion_zone_detection',
    default_args=default_args,
    description='Détection rapide de congestion par zones géographiques (sans mapmatching)',
    schedule_interval='*/10 * * * *',  # Exécution toutes les 10 minutes
    catchup=False,
    tags=['congestion', 'traffic', 'quick']
) as dag_congestion:

    extract = PythonOperator(
        task_id='extract_data',
        python_callable=extract_task,
    )

    clean = PythonOperator(
        task_id='clean_data',
        python_callable=clean_task,
    )

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

    extract >> clean >> detect >> aggregate_zone >> load_congestion

# DAG 2: Mapmatching et analyse avancée (toutes les 30 minutes) - AVEC mapmatching
# Ce DAG est plus lourd, nécessite mapmatching pour l'agrégation par edge, ML et alertes

with DAG(
    'traffic_advanced_analysis',
    default_args=default_args,
    description='Analyse avancée du trafic avec mapmatching, ML et alertes',
    schedule_interval='*/30 * * * *',  # Exécution toutes les 30 minutes
    catchup=False,
    tags=['traffic', 'prediction', 'mapmatching', 'alerts']
) as dag_advanced:

    extract_advanced = PythonOperator(
        task_id='extract_data',
        python_callable=extract_task,
    )

    clean_advanced = PythonOperator(
        task_id='clean_data',
        python_callable=clean_task,
    )

    mapmatching = PythonOperator(
        task_id='mapmatching',
        python_callable=mapmatching_task,
        **mapmatching_args,
        # OPTIMISATION: Permettre à la tâche suivante de continuer même si mapmatching timeout
        # Retourner un DataFrame vide plutôt que d'échouer pour ne pas bloquer
        do_xcom_push=True,  # Push le résultat même en cas d'erreur
    )

    aggregate_edge = PythonOperator(
        task_id='aggregate_edge',
        python_callable=aggregate_by_edge_task,
    )

    load_edge_agg = PythonOperator(
        task_id='load_edge_agg',
        python_callable=load_edge_agg_task,
    )

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

    # OPTIMISATION: Permettre aux tâches suivantes de s'exécuter même si mapmatching échoue ou timeout
    # Utiliser 'all_done' pour que aggregate_edge s'exécute même si mapmatching échoue
    extract_advanced >> clean_advanced >> mapmatching >> aggregate_edge >> load_edge_agg
    
    # ML et prédictions s'exécutent après edge_agg
    load_edge_agg >> train_ml >> predict >> load_predictions
    
    # Note: Les alertes proactives sont maintenant gérées par le DAG séparé 'proactive_alerts'
    # qui s'exécute toutes les 10 minutes pour une meilleure réactivité
    # Le DAG proactive_alerts ne nécessite pas mapmatching, il utilise directement edge_agg
    
    # Rendre les tâches tolérantes aux échecs - elles s'exécutent même si mapmatching échoue
    # 'all_done' = s'exécute même si les tâches précédentes ont échoué ou timeout
    aggregate_edge.trigger_rule = 'all_done'
    load_edge_agg.trigger_rule = 'all_done'
    train_ml.trigger_rule = 'all_done'
    predict.trigger_rule = 'all_done'
    load_predictions.trigger_rule = 'all_done'
    
    # OPTIMISATION: Permettre à aggregate_edge de s'exécuter même si mapmatching timeout
    # Si mapmatching échoue ou timeout, aggregate_edge recevra un DataFrame vide
    # et retournera un DataFrame vide sans bloquer le reste du pipeline
    load_predictions.trigger_rule = 'all_done'
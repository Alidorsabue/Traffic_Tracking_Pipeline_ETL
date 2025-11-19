# dags/Mapmatching_DAG.py
"""
DAG pour effectuer le map matching des données GPS récentes.
S'exécute une fois par heure et stocke les résultats dans mapmatching_cache pour réutilisation.
Cela évite de bloquer le pipeline principal avec le map matching à chaque exécution.
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
    'retry_delay': timedelta(minutes=10),
    'email_on_failure': False,
    'email_on_retry': False,
}

def mapmatching_cache_task(**context):
    """
    Effectue le map matching sur les données GPS récentes et stocke les résultats dans mapmatching_cache.
    Cette tâche s'exécute toutes les heures pour maintenir un cache à jour.
    """
    try:
        # Import lazy pour éviter le timeout au chargement du DAG
        from src.mapmatching import effectuer_mapmatching
        from src.Script_ETL import extract_recent_data, clean_data, get_db_connection
        import pandas as pd
        
        print("🔄 Début du map matching pour le cache...")
        
        # Extraire les données récentes (dernière heure)
        print("📥 Extraction des données GPS récentes (dernière heure)...")
        df = extract_recent_data()
        
        if df.empty:
            print("⚠️ Aucune donnée GPS récente à traiter")
            return "no_data"
        
        print(f"✅ {len(df)} points GPS extraits")
        
        # Nettoyer les données
        print("🧹 Nettoyage des données...")
        df_clean = clean_data(df)
        
        if df_clean.empty:
            print("⚠️ Aucune donnée valide après nettoyage")
            return "no_valid_data"
        
        print(f"✅ {len(df_clean)} points GPS valides après nettoyage")
        
        # OPTIMISATION: Traiter un maximum de points mais avec une limite raisonnable
        # Pour le cache horaire, on peut traiter plus de points qu'en temps réel
        max_points_to_process = 100  # Plus que le DAG principal car on a plus de temps
        
        if len(df_clean) > max_points_to_process:
            # Prendre les 100 points les plus récents
            df_limited = df_clean.head(max_points_to_process)
            print(f"⚠️ Mapmatching limité à {max_points_to_process} points (sur {len(df_clean)} disponibles)")
        else:
            df_limited = df_clean
            print(f"Début mapmatching sur {len(df_limited)} points")
        
        # Exécuter map matching
        print("🗺️ Exécution du map matching...")
        df_matched = effectuer_mapmatching(df_limited, max_points=max_points_to_process, max_distance=50)
        
        if df_matched.empty:
            print("⚠️ Aucun résultat après map matching")
            return "no_match_result"
        
        # Compter les points matchés
        matched_count = df_matched['edge_u'].notna().sum() if 'edge_u' in df_matched.columns else 0
        print(f"✅ Map matching terminé: {matched_count}/{len(df_matched)} points matchés ({matched_count/len(df_matched)*100:.1f}%)")
        
        # Stocker dans mapmatching_cache
        print("💾 Stockage des résultats dans mapmatching_cache...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Préparer les données pour insertion
            # Colonnes nécessaires: driver_id, latitude, longitude, speed, timestamp, edge_u, edge_v
            required_cols = ['driver_id', 'latitude', 'longitude', 'speed', 'timestamp']
            optional_cols = ['edge_u', 'edge_v', 'osmid', 'road_name', 'distance_to_road']
            
            # Vérifier que les colonnes requises existent
            missing_cols = set(required_cols) - set(df_matched.columns)
            if missing_cols:
                print(f"❌ Colonnes manquantes: {missing_cols}")
                return "missing_columns"
            
            # Sélectionner les colonnes à insérer
            cols_to_insert = required_cols.copy()
            for col in optional_cols:
                if col in df_matched.columns:
                    cols_to_insert.append(col)
            
            df_to_insert = df_matched[cols_to_insert].copy()
            
            # Ajouter une colonne processed_at pour marquer quand ces données ont été traitées
            df_to_insert['processed_at'] = datetime.now()
            
            # Insérer les données (remplacer les anciennes données pour la même période)
            # On supprime d'abord les données de la dernière heure pour éviter les doublons
            delete_query = """
                DELETE FROM mapmatching_cache 
                WHERE processed_at > NOW() - INTERVAL '2 hours'
            """
            cursor.execute(delete_query)
            deleted_count = cursor.rowcount
            print(f"🗑️ {deleted_count} anciennes entrées supprimées du cache")
            
            # Insérer les nouvelles données
            insert_query = """
                INSERT INTO mapmatching_cache 
                (driver_id, latitude, longitude, speed, timestamp, edge_u, edge_v, osmid, road_name, distance_to_road, processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (driver_id, timestamp) DO UPDATE SET
                    edge_u = EXCLUDED.edge_u,
                    edge_v = EXCLUDED.edge_v,
                    osmid = EXCLUDED.osmid,
                    road_name = EXCLUDED.road_name,
                    distance_to_road = EXCLUDED.distance_to_road,
                    processed_at = EXCLUDED.processed_at
            """
            
            values = []
            for _, row in df_to_insert.iterrows():
                values.append((
                    str(row['driver_id']),
                    float(row['latitude']),
                    float(row['longitude']),
                    float(row['speed']),
                    row['timestamp'] if pd.notna(row['timestamp']) else datetime.now(),
                    int(row['edge_u']) if pd.notna(row.get('edge_u')) else None,
                    int(row['edge_v']) if pd.notna(row.get('edge_v')) else None,
                    int(row['osmid']) if pd.notna(row.get('osmid')) else None,
                    str(row['road_name']) if pd.notna(row.get('road_name')) else None,
                    float(row['distance_to_road']) if pd.notna(row.get('distance_to_road')) else None,
                    row['processed_at']
                ))
            
            from psycopg2.extras import execute_values
            execute_values(cursor, insert_query, values)
            conn.commit()
            
            print(f"✅ {len(values)} entrées ajoutées au cache mapmatching")
            return "success"
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Erreur lors de l'insertion dans mapmatching_cache: {e}")
            import traceback
            traceback.print_exc()
            return "insert_error"
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        print(f"❌ Erreur dans mapmatching_cache_task: {e}")
        import traceback
        traceback.print_exc()
        return "error"

with DAG(
    'mapmatching_cache_hourly',
    default_args=default_args,
    description='Effectue le map matching toutes les heures et stocke les résultats dans le cache',
    schedule_interval='0 * * * *',  # Toutes les heures à minute 0
    catchup=False,
    tags=['mapmatching', 'cache', 'hourly'],
    max_active_runs=1  # Une seule exécution à la fois
) as dag:

    mapmatching_cache = PythonOperator(
        task_id='mapmatching_cache',
        python_callable=mapmatching_cache_task,
        execution_timeout=timedelta(minutes=30),  # Timeout de 30 minutes pour cette tâche
    )

    mapmatching_cache


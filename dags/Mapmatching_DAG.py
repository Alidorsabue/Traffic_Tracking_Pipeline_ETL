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
    Version améliorée avec meilleure gestion des erreurs et logging détaillé.
    """
    import time
    start_time = time.time()
    
    try:
        # Import lazy pour éviter le timeout au chargement du DAG
        from src.mapmatching import effectuer_mapmatching, telecharger_reseau
        from src.Script_ETL import extract_recent_data, clean_data, get_db_connection
        import pandas as pd
        
        print("=" * 80)
        print("🔄 DÉBUT DU MAP MATCHING POUR LE CACHE")
        print("=" * 80)
        print(f"Timestamp: {datetime.now()}\n")
        
        # ÉTAPE 1: Extraction des données GPS depuis la table gps_points
        # IMPORTANT: Cette étape lit les données GPS collectées par l'app mobile
        print("[ÉTAPE 1/5] 📥 Extraction des données GPS depuis gps_points (app mobile)...")
        try:
            # extract_recent_data() lit depuis la table gps_points:
            # SELECT driver_id, latitude, longitude, speed, timestamp FROM gps_points
            df = extract_recent_data()
            
            if df is None:
                print("❌ ERREUR: extract_recent_data() a retourné None")
                return "extraction_error"
            
            if df.empty:
                print("⚠️ Aucune donnée GPS récente à traiter")
                print("   Vérifier que la table gps_points contient des données récentes")
                print("   Vérifier que l'app mobile envoie bien les données à la base de données")
                return "no_data"
            
            print(f"✅ {len(df)} points GPS extraits depuis gps_points")
            print(f"   Colonnes: {list(df.columns)}")
            if not df.empty:
                print(f"   Exemple: driver_id={df['driver_id'].iloc[0]}, lat={df['latitude'].iloc[0]:.6f}, lon={df['longitude'].iloc[0]:.6f}")
            elapsed = time.time() - start_time
            print(f"   Temps écoulé: {elapsed:.2f}s\n")
            
        except Exception as e:
            print(f"❌ ERREUR lors de l'extraction des données GPS: {e}")
            import traceback
            traceback.print_exc()
            return "extraction_error"
        
        # ÉTAPE 2: Nettoyage des données
        print("[ÉTAPE 2/5] 🧹 Nettoyage des données...")
        try:
            df_clean = clean_data(df)
            
            if df_clean.empty:
                print("⚠️ Aucune donnée valide après nettoyage")
                print("   Les données GPS ont peut-être été filtrées (vitesses aberrantes, doublons)")
                return "no_valid_data"
            
            print(f"✅ {len(df_clean)} points GPS valides après nettoyage")
            print(f"   {len(df) - len(df_clean)} points filtrés")
            elapsed = time.time() - start_time
            print(f"   Temps écoulé: {elapsed:.2f}s\n")
            
        except Exception as e:
            print(f"❌ ERREUR lors du nettoyage: {e}")
            import traceback
            traceback.print_exc()
            return "cleaning_error"
        
        # ÉTAPE 3: Préparation des données pour mapmatching
        print("[ÉTAPE 3/5] 🔧 Préparation des données pour mapmatching...")
        try:
            # OPTIMISATION: Réduire le nombre de points pour éviter les timeouts
            # 100 points peuvent prendre 28 minutes, réduisons à 50
            max_points_to_process = 50
            
            if len(df_clean) > max_points_to_process:
                df_limited = df_clean.head(max_points_to_process)
                print(f"⚠️ Mapmatching limité à {max_points_to_process} points (sur {len(df_clean)} disponibles)")
            else:
                df_limited = df_clean
                print(f"✅ {len(df_limited)} points à traiter")
            
            # Vérifier les coordonnées
            invalid_coords = df_limited[
                (df_limited['latitude'].isna()) | 
                (df_limited['longitude'].isna()) |
                (df_limited['latitude'] < -90) | (df_limited['latitude'] > 90) |
                (df_limited['longitude'] < -180) | (df_limited['longitude'] > 180)
            ]
            if not invalid_coords.empty:
                print(f"⚠️ {len(invalid_coords)} points avec coordonnées invalides seront ignorés")
                df_limited = df_limited.drop(invalid_coords.index)
            
            if df_limited.empty:
                print("❌ Aucun point valide après vérification des coordonnées")
                return "no_valid_coords"
            
            elapsed = time.time() - start_time
            print(f"   Temps écoulé: {elapsed:.2f}s\n")
            
        except Exception as e:
            print(f"❌ ERREUR lors de la préparation: {e}")
            import traceback
            traceback.print_exc()
            return "preparation_error"
        
        # ÉTAPE 4: Exécution du map matching
        # IMPORTANT: Cette étape associe les points GPS collectés (gps_points) aux routes (OpenStreetMap)
        print("[ÉTAPE 4/5] 🗺️ Exécution du map matching...")
        print("   FLUX: Points GPS (gps_points) ← App mobile")
        print("         Réseau routier (OSM) ← OpenStreetMap (téléchargé)")
        print("         Association ← Trouver la route la plus proche de chaque point GPS")
        print("   Cette étape peut prendre plusieurs minutes...")
        mapmatching_start = time.time()
        
        try:
            # effectuer_mapmatching() va:
            # 1. Prendre les points GPS de df_limited (qui viennent de gps_points)
            # 2. Télécharger le réseau routier depuis OpenStreetMap pour Kinshasa
            # 3. Associer chaque point GPS au tronçon de route le plus proche
            df_matched = effectuer_mapmatching(
                df_limited,  # Points GPS collectés depuis gps_points
                max_points=max_points_to_process, 
                max_distance=50,
                place="Kinshasa, Democratic Republic of the Congo"  # Lieu pour télécharger le réseau OSM
            )
            
            mapmatching_elapsed = time.time() - mapmatching_start
            print(f"✅ Map matching terminé en {mapmatching_elapsed:.2f}s")
            
            if df_matched is None:
                print("❌ ERREUR: effectuer_mapmatching() a retourné None")
                return "mapmatching_returned_none"
            
            if df_matched.empty:
                print("⚠️ Aucun résultat après map matching")
                print("   Cela peut arriver si:")
                print("   - Le réseau routier n'a pas pu être téléchargé")
                print("   - Les points GPS sont trop éloignés des routes (> 50m)")
                return "no_match_result"
            
            # Compter les points matchés
            if 'edge_u' in df_matched.columns:
                matched_count = df_matched['edge_u'].notna().sum()
                match_rate = (matched_count / len(df_matched) * 100) if len(df_matched) > 0 else 0
                print(f"✅ {matched_count}/{len(df_matched)} points matchés ({match_rate:.1f}%)")
                
                if matched_count == 0:
                    print("⚠️ ATTENTION: Aucun point n'a été matché à une route")
                    print("   Les données seront quand même sauvegardées pour référence")
            else:
                print("⚠️ Colonne 'edge_u' manquante dans le résultat")
                matched_count = 0
            
            elapsed = time.time() - start_time
            print(f"   Temps écoulé total: {elapsed:.2f}s\n")
            
        except Exception as e:
            mapmatching_elapsed = time.time() - mapmatching_start
            print(f"❌ ERREUR lors du map matching après {mapmatching_elapsed:.2f}s: {e}")
            import traceback
            traceback.print_exc()
            print("\nCauses possibles:")
            print("   - Problème de connexion internet (téléchargement réseau routier)")
            print("   - Timeout lors du téléchargement du réseau routier")
            print("   - Erreur dans OSMnx ou GeoPandas")
            return "mapmatching_error"
        
        # ÉTAPE 5: Stockage dans mapmatching_cache
        print("[ÉTAPE 5/5] 💾 Stockage des résultats dans mapmatching_cache...")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Préparer les données pour insertion
            required_cols = ['driver_id', 'latitude', 'longitude', 'speed', 'timestamp']
            optional_cols = ['edge_u', 'edge_v', 'osmid', 'road_name', 'distance_to_road']
            
            # Vérifier que les colonnes requises existent
            missing_cols = set(required_cols) - set(df_matched.columns)
            if missing_cols:
                print(f"❌ Colonnes manquantes: {missing_cols}")
                cursor.close()
                conn.close()
                return "missing_columns"
            
            # Sélectionner les colonnes à insérer
            cols_to_insert = required_cols.copy()
            for col in optional_cols:
                if col in df_matched.columns:
                    cols_to_insert.append(col)
            
            df_to_insert = df_matched[cols_to_insert].copy()
            
            # Ajouter une colonne processed_at
            df_to_insert['processed_at'] = datetime.now()
            
            # Supprimer les anciennes données (dernières 2 heures)
            delete_query = """
                DELETE FROM mapmatching_cache 
                WHERE processed_at > NOW() - INTERVAL '2 hours'
            """
            cursor.execute(delete_query)
            deleted_count = cursor.rowcount
            print(f"🗑️ {deleted_count} anciennes entrées supprimées du cache")
            
            # Préparer les valeurs pour insertion
            values = []
            for _, row in df_to_insert.iterrows():
                try:
                    values.append((
                        str(row['driver_id']) if pd.notna(row['driver_id']) else None,
                        float(row['latitude']) if pd.notna(row['latitude']) else None,
                        float(row['longitude']) if pd.notna(row['longitude']) else None,
                        float(row['speed']) if pd.notna(row['speed']) else None,
                        row['timestamp'] if pd.notna(row['timestamp']) else datetime.now(),
                        int(row['edge_u']) if 'edge_u' in row and pd.notna(row.get('edge_u')) else None,
                        int(row['edge_v']) if 'edge_v' in row and pd.notna(row.get('edge_v')) else None,
                        int(row['osmid']) if 'osmid' in row and pd.notna(row.get('osmid')) else None,
                        str(row['road_name']) if 'road_name' in row and pd.notna(row.get('road_name')) else None,
                        float(row['distance_to_road']) if 'distance_to_road' in row and pd.notna(row.get('distance_to_road')) else None,
                        row['processed_at']
                    ))
                except Exception as e_row:
                    print(f"⚠️ Erreur lors de la préparation d'une ligne: {e_row}")
                    continue
            
            if not values:
                print("❌ Aucune valeur valide à insérer")
                conn.rollback()
                cursor.close()
                conn.close()
                return "no_valid_values"
            
            # Insérer les données
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
            
            from psycopg2.extras import execute_values
            execute_values(cursor, insert_query, values, page_size=100)
            conn.commit()
            
            total_elapsed = time.time() - start_time
            print(f"✅ {len(values)} entrées ajoutées au cache mapmatching")
            print(f"✅ Tâche terminée avec succès en {total_elapsed:.2f}s")
            print("=" * 80)
            
            cursor.close()
            conn.close()
            return "success"
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"❌ Erreur lors de l'insertion dans mapmatching_cache: {e}")
            import traceback
            traceback.print_exc()
            return "insert_error"
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            
    except Exception as e:
        total_elapsed = time.time() - start_time
        print(f"❌ ERREUR CRITIQUE dans mapmatching_cache_task après {total_elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return "critical_error"

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
        execution_timeout=timedelta(minutes=45),  # Timeout augmenté à 45 minutes (28 min observé + marge)
    )

    mapmatching_cache


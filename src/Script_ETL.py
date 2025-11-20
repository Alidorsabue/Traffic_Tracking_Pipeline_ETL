# Ce script est utilisé pour extraire les données récentes de la base de 
# données et les stocker dans un fichier CSV.
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os

def get_db_connection():
    """
    Crée une connexion à PostgreSQL en utilisant les variables d'environnement.
    - Dans Docker (Airflow): utilise le service postgres si disponible
    - En local: utilise les variables d'environnement ou valeurs par défaut pour dev
    """
    import locale
    import sys
    
    def safe_decode(value, default=''):
        """Décode une valeur en UTF-8 en gérant plusieurs encodages."""
        if value is None:
            return default
        if isinstance(value, str):
            return value
        if isinstance(value, bytes):
            # Essayer UTF-8 d'abord
            try:
                return value.decode('utf-8')
            except UnicodeDecodeError:
                # Essayer l'encodage du système (Windows-1252, latin-1, etc.)
                try:
                    return value.decode(locale.getpreferredencoding())
                except (UnicodeDecodeError, LookupError):
                    try:
                        return value.decode('latin-1')  # Fallback: latin-1 peut décoder n'importe quel byte
                    except:
                        return value.decode('utf-8', errors='replace')  # Dernier recours: remplacer les erreurs
        return str(value)
    
    try:
        # Détecter si on est dans Docker (environnement Airflow)
        is_docker = os.path.exists('/.dockerenv') or os.environ.get('AIRFLOW_HOME') is not None
        
        # Récupérer les valeurs depuis les variables d'environnement
        # En production, utiliser africaits.com par défaut
        if is_docker:
            # Dans Docker, utiliser le serveur de production par défaut
            host_raw = os.getenv('POSTGRES_HOST', 'africaits.com')
            port_raw = os.getenv('POSTGRES_PORT', '5432')
        else:
            # En local, utiliser localhost (mais peut être surchargé par env vars)
            host_raw = os.getenv('POSTGRES_HOST', 'africaits.com')  # Utiliser africaits.com même en local si non défini
            port_raw = os.getenv('POSTGRES_PORT', '5432')
        
        database_raw = os.getenv('POSTGRES_DB', 'Traffic_Tracking')
        user_raw = os.getenv('POSTGRES_USER', 'Alidorsabue')
        password_raw = os.getenv('POSTGRES_PASSWORD', 'Virgi@1996')
        
        # Décoder toutes les valeurs en gérant les problèmes d'encodage
        host = safe_decode(host_raw)
        port = int(safe_decode(port_raw, '5432'))
        database = safe_decode(database_raw)
        user = safe_decode(user_raw)
        password = safe_decode(password_raw)
        
        # En production, vérifier que les credentials sont configurés
        if os.getenv('ENVIRONMENT') == 'production' and password in ['postgres', '']:
            raise ValueError("POSTGRES_PASSWORD doit être configuré en production !")
        
        # Convertir tout en str pour éviter les problèmes
        host = str(host) if host else 'localhost'
        database = str(database) if database else 'Traffic_Tracking'
        user = str(user) if user else 'postgres'
        password = str(password) if password else ''
        
        # Utiliser des paramètres explicites plutôt qu'un DSN pour éviter les problèmes d'encodage
        # Ne pas utiliser de DSN string qui peut causer des problèmes d'encodage
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            client_encoding='UTF8',
            connect_timeout=10
        )
        return conn
    except UnicodeDecodeError as e:
        print(f"❌ ERREUR d'encodage lors de la connexion à la base de données: {e}")
        print(f"   Position de l'erreur: {e.start if hasattr(e, 'start') else 'N/A'}")
        print(f"   Vérifier que les variables d'environnement sont correctement configurées")
        print(f"   Solution: Définir les variables d'environnement explicitement en UTF-8")
        raise
    except psycopg2.OperationalError as e:
        print(f"❌ ERREUR de connexion à la base de données: {e}")
        print(f"   Host: {host if 'host' in locals() else 'N/A'}")
        print(f"   Port: {port if 'port' in locals() else 'N/A'}")
        print(f"   Database: {database if 'database' in locals() else 'N/A'}")
        print(f"   User: {user if 'user' in locals() else 'N/A'}")
        raise
    except Exception as e:
        print(f"❌ ERREUR lors de la connexion à la base de données: {type(e).__name__}: {e}")
        print(f"   Host: {host if 'host' in locals() else 'N/A'}")
        print(f"   Port: {port if 'port' in locals() else 'N/A'}")
        print(f"   Database: {database if 'database' in locals() else 'N/A'}")
        print(f"   User: {user if 'user' in locals() else 'N/A'}")
        raise

def extract_recent_data():
    """
    Extrait les données GPS récentes de la table gps_points.
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame avec les colonnes driver_id, latitude, longitude, speed, timestamp
        DataFrame vide si aucune donnée trouvée
    """
    try:
        conn = get_db_connection()
        
        # Vérifier d'abord si la table existe et contient des données
        check_query = """
        SELECT COUNT(*) as total_count,
               MAX(timestamp) as latest_timestamp
        FROM gps_points
        """
        check_result = pd.read_sql(check_query, conn)
        
        if check_result.empty or check_result['total_count'].iloc[0] == 0:
            print("⚠️ La table gps_points est vide ou n'existe pas")
            conn.close()
            return pd.DataFrame()
        
        total_count = int(check_result['total_count'].iloc[0])
        latest_timestamp = check_result['latest_timestamp'].iloc[0]
        print(f"📊 Table gps_points: {total_count} lignes au total, dernière donnée: {latest_timestamp}")
        
        # Essayer d'abord les 30 dernières minutes
        query = """
        SELECT driver_id, latitude, longitude, speed, timestamp
        FROM gps_points
        WHERE timestamp > NOW() - INTERVAL '30 minutes'
        ORDER BY timestamp DESC
        LIMIT 1000;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Si pas de données récentes, charger toutes les données disponibles (récentes)
        if df.empty:
            print("⚠️ Aucune donnée dans les 30 dernières minutes, récupération de toutes les données disponibles...")
            conn = get_db_connection()
            query_all = """
            SELECT driver_id, latitude, longitude, speed, timestamp
            FROM gps_points
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            ORDER BY timestamp DESC
            LIMIT 1000
            """
            df = pd.read_sql(query_all, conn)
            conn.close()
            
            if df.empty:
                print("⚠️ Aucune donnée trouvée même dans les 24 dernières heures")
                print("   Vérifier que l'app mobile envoie des données à la base de données")
            else:
                print(f"✅ {len(df)} lignes récupérées (dernières 24 heures)")
        
        return df
        
    except Exception as e:
        print(f"❌ ERREUR lors de l'extraction des données GPS: {e}")
        import traceback
        traceback.print_exc()
        try:
            if conn:
                conn.close()
        except:
            pass
        return pd.DataFrame()

def load_mapmatching_from_cache(hours_back=1):
    """
    Charge les résultats de map matching depuis le cache.
    
    Parameters:
    -----------
    hours_back : int
        Nombre d'heures en arrière pour récupérer les données (par défaut: 1 heure)
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame avec les colonnes driver_id, latitude, longitude, speed, timestamp, edge_u, edge_v, etc.
        DataFrame vide si aucune donnée trouvée
    """
    conn = get_db_connection()
    
    try:
        query = f"""
            SELECT driver_id, latitude, longitude, speed, timestamp, 
                   edge_u, edge_v, osmid, road_name, distance_to_road
            FROM mapmatching_cache
            WHERE processed_at > NOW() - INTERVAL '{hours_back} hours'
              AND timestamp > NOW() - INTERVAL '{hours_back} hours'
            ORDER BY timestamp DESC
        """
        
        # Utiliser les mêmes heures pour processed_at et timestamp pour cohérence
        df = pd.read_sql(query, conn)
        
        if df.empty:
            print(f"Aucune donnée dans mapmatching_cache pour les {hours_back} dernières heures")
            return pd.DataFrame()
        
        print(f"✅ {len(df)} points chargés depuis mapmatching_cache")
        return df
        
    except Exception as e:
        print(f"Erreur lors du chargement depuis mapmatching_cache: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        conn.close()

# Transformation (nettoyage + agrégation + détection de congestion)
    # Supprimer les doublons, 
    # Supprimer les vitesses nulles ou aberrantes (ex. > 150 km/h)
    # Ajouter une colonne d’heure

def clean_data(df):
    # Gérer le cas où le DataFrame est vide
    if df.empty:
        return df
    
    df = df.drop_duplicates()
    # Filtrer uniquement les vitesses aberrantes (> 150 km/h)
    # Accepter les vitesses de 0 à 150 km/h (inclure les véhicules à l'arrêt)
    df = df[df['speed'] <= 150]
    df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
    return df

# Détection d’embouteillage : On utilise un seuil dynamique selon l’heure
def detect_congestion(df):
    # Gérer le cas où le DataFrame est vide
    if df.empty:
        return df
    
    conditions = [
        (df['hour'].between(6, 9)) | (df['hour'].between(16, 19)),  # heures de pointe                                                                          
        (df['hour'].between(0, 5)) | (df['hour'].between(20, 23))   # nuit      
    ]
    speed_limits = [10, 5]  # seuils km/h
    df['is_congested'] = False
    for cond, limit in zip(conditions, speed_limits):
        df.loc[cond & (df['speed'] < limit), 'is_congested'] = True
    return df

# Agrégation spatiale : On regroupe par zones (ou par grille de coordonnées) pour calculer la vitesse moyenne par zone

def aggregate_by_zone(df, grid_size=0.001):  # ~100 m
    # Gérer le cas où le DataFrame est vide
    if df.empty:
        return pd.DataFrame(columns=['lat_bin', 'lon_bin', 'avg_speed', 'congestion_rate'])
    
    df['lat_bin'] = (df['latitude'] // grid_size) * grid_size
    df['lon_bin'] = (df['longitude'] // grid_size) * grid_size
    agg = df.groupby(['lat_bin', 'lon_bin']).agg(
        avg_speed=('speed', 'mean'),
        congestion_rate=('is_congested', 'mean')
    ).reset_index()
    return agg

# Sauvegarde des données transformées : enregistrement des données dans la base de données

def load_to_db(df):
    """
    Insère les données de congestion dans la table congestion.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame avec les colonnes lat_bin, lon_bin, avg_speed, congestion_rate
    
    Returns:
    --------
    bool
        True si l'insertion a réussi, False sinon
    """
    if df is None or df.empty:
        print("load_to_db: DataFrame vide, aucune donnée de congestion à charger")
        return False
    
    required_cols = ['lat_bin', 'lon_bin', 'avg_speed', 'congestion_rate']
    if not all(col in df.columns for col in required_cols):
        missing = set(required_cols) - set(df.columns)
        print(f"Erreur: Colonnes manquantes pour l'insertion dans congestion: {missing}")
        print(f"Colonnes disponibles: {list(df.columns)}")
        return False
    
    conn = None
    cursor = None
    try:
        print(f"Chargement de {len(df)} lignes dans la table congestion...")
        conn = get_db_connection()
        cursor = conn.cursor()

        # Convertir le DataFrame en liste de tuples Python natifs
        values = df[['lat_bin', 'lon_bin', 'avg_speed', 'congestion_rate']].values.tolist()
        values = [
            (float(v[0]), float(v[1]), float(v[2]), float(v[3]))
            for v in values
        ]

        # Utiliser executemany pour insérer toutes les lignes
        cursor.executemany(
            """
            INSERT INTO congestion (lat_bin, lon_bin, avg_speed, congestion_rate)
            VALUES (%s, %s, %s, %s)
            """,
            values
        )
        
        conn.commit()
        print(f"Données de congestion chargées avec succès: {len(values)} lignes insérées")
        return True
        
    except Exception as e:
        print(f"Erreur lors du chargement des données de congestion dans la base: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
def aggregate_by_edge(df, time_interval_minutes=10):
    """
    Agrège les données GPS par tronçon de route (edge_u, edge_v) et par intervalle de temps.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame avec les colonnes edge_u, edge_v, speed, timestamp (après map matching)
    time_interval_minutes : int
        Intervalle de temps en minutes pour l'agrégation (par défaut: 10)
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame agrégé avec edge_u, edge_v, ts, avg_speed_kmh
    """
    if df.empty:
        return pd.DataFrame(columns=['edge_u', 'edge_v', 'ts', 'avg_speed_kmh'])
    
    required_cols = ['edge_u', 'edge_v', 'speed', 'timestamp']
    if not all(col in df.columns for col in required_cols):
        missing = set(required_cols) - set(df.columns)
        print(f"Avertissement: Colonnes manquantes pour l'agrégation par edge: {missing}")
        return pd.DataFrame(columns=['edge_u', 'edge_v', 'ts', 'avg_speed_kmh'])
    
    df = df.copy()
    df = df[df['edge_u'].notna() & df['edge_v'].notna()]
    
    if df.empty:
        return pd.DataFrame(columns=['edge_u', 'edge_v', 'ts', 'avg_speed_kmh'])
    
    if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    df['ts'] = df['timestamp'].dt.floor(f'{time_interval_minutes}min')
    
    agg = df.groupby(['edge_u', 'edge_v', 'ts']).agg(
        avg_speed_kmh=('speed', 'mean')
    ).reset_index()
    
    return agg

def load_edge_agg_to_db(df):
    """
    Insère les données agrégées par edge dans la table edge_agg.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame avec les colonnes edge_u, edge_v, ts, avg_speed_kmh
    
    Returns:
    --------
    bool
        True si l'insertion a réussi, False sinon
    """
    if df is None or df.empty:
        print("load_edge_agg_to_db: DataFrame vide, aucune donnée à charger")
        return False
    
    required_cols = ['edge_u', 'edge_v', 'ts', 'avg_speed_kmh']
    if not all(col in df.columns for col in required_cols):
        missing = set(required_cols) - set(df.columns)
        print(f"Erreur: Colonnes manquantes pour l'insertion dans edge_agg: {missing}")
        print(f"Colonnes disponibles: {list(df.columns)}")
        return False
    
    conn = None
    cursor = None
    try:
        print(f"Chargement de {len(df)} lignes dans edge_agg...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        values = df[['edge_u', 'edge_v', 'ts', 'avg_speed_kmh']].values.tolist()
        values = [
            (int(v[0]), int(v[1]), pd.Timestamp(v[2]), float(v[3]))
            for v in values
        ]
        
        cursor.executemany(
            """
            INSERT INTO edge_agg (edge_u, edge_v, ts, avg_speed_kmh)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (edge_u, edge_v, ts) DO UPDATE
            SET avg_speed_kmh = EXCLUDED.avg_speed_kmh
            """,
            values
        )
        
        conn.commit()
        print(f"Données edge_agg chargées avec succès: {len(values)} lignes insérées/mises à jour")
        return True
        
    except Exception as e:
        print(f"Erreur lors du chargement des données edge_agg dans la base: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def load_predictions_to_db(df):
    """
    Insère les prédictions de vitesse dans la table predictions.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame avec les colonnes edge_u, edge_v, ts, pred_speed_kmh
    
    Returns:
    --------
    bool
        True si l'insertion a réussi, False sinon
    """
    if df is None or df.empty:
        print("load_predictions_to_db: DataFrame vide, aucune prédiction à charger")
        return False
    
    required_cols = ['edge_u', 'edge_v', 'ts', 'pred_speed_kmh']
    if not all(col in df.columns for col in required_cols):
        missing = set(required_cols) - set(df.columns)
        print(f"Erreur: Colonnes manquantes pour l'insertion dans predictions: {missing}")
        print(f"Colonnes disponibles: {list(df.columns)}")
        return False
    
    conn = None
    cursor = None
    try:
        print(f"Chargement de {len(df)} prédictions dans la table predictions...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        values = df[['edge_u', 'edge_v', 'ts', 'pred_speed_kmh']].values.tolist()
        values = [
            (int(v[0]), int(v[1]), pd.Timestamp(v[2]), float(v[3]))
            for v in values
        ]
        
        cursor.executemany(
            """
            INSERT INTO predictions (edge_u, edge_v, ts, pred_speed_kmh)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (edge_u, edge_v, ts) DO UPDATE
            SET pred_speed_kmh = EXCLUDED.pred_speed_kmh, created_at = CURRENT_TIMESTAMP
            """,
            values
        )
        
        conn.commit()
        print(f"Prédictions chargées avec succès: {len(values)} lignes insérées/mises à jour dans predictions")
        return True
        
    except Exception as e:
        print(f"Erreur lors du chargement des prédictions dans la base: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

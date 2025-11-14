# Module pour gérer les alertes de congestion aux chauffeurs
# Fonctions extraites de alert_api.py pour être utilisables dans Airflow

from sqlalchemy import create_engine
from twilio.rest import Client
import pandas as pd
import time
import os
import psycopg2

# Import lazy pour OSMnx (évite les timeouts au chargement)
# OSMnx sera importé seulement quand nécessaire

# Configuration de la base de données PostgreSQL
# Utilise la même logique de connexion que les autres scripts

def get_db_connection():
    """
    Crée une connexion PostgreSQL en utilisant les variables d'environnement.
    - Dans Docker (Airflow): utilise le service postgres si disponible
    - En local: utilise les variables d'environnement
    
    Raises:
    -------
    psycopg2.Error
        Si la connexion à la base de données échoue
    ValueError
        Si les credentials ne sont pas configurés en production
    """
    try:
        is_docker = os.path.exists('/.dockerenv') or os.environ.get('AIRFLOW_HOME') is not None
        
        # Récupérer les valeurs depuis les variables d'environnement
        # En production, utiliser africaits.com par défaut
        if is_docker:
            host = os.getenv('POSTGRES_HOST', 'africaits.com')
            port = int(os.getenv('POSTGRES_PORT', '5432'))
        else:
            # En local, utiliser localhost ou host.docker.internal
            host = os.getenv('POSTGRES_HOST', 'localhost')
            port = int(os.getenv('POSTGRES_PORT', '5433'))
        
        database = os.getenv('POSTGRES_DB', 'Traffic_Tracking')
        user = os.getenv('POSTGRES_USER', 'Alidorsabue')
        password = os.getenv('POSTGRES_PASSWORD', 'Virgi@1996')
        
        # En production, vérifier que les credentials sont configurés
        if os.getenv('ENVIRONMENT') == 'production' and password in ['postgres', '']:
            raise ValueError("POSTGRES_PASSWORD doit être configuré en production !")
        
        return psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
    except psycopg2.OperationalError as e:
        print(f"Erreur de connexion à la base de données: {e}")
        raise
    except Exception as e:
        print(f"Erreur inattendue lors de la connexion à la base de données: {e}")
        raise

def get_db_uri():
    """
    Crée une URI SQLAlchemy en utilisant les variables d'environnement.
    - Dans Docker (Airflow): utilise le service postgres si disponible
    - En local: utilise les variables d'environnement
    """
    is_docker = os.path.exists('/.dockerenv') or os.environ.get('AIRFLOW_HOME') is not None
    
    # Récupérer les valeurs depuis les variables d'environnement
    # En production, utiliser africaits.com par défaut
    if is_docker:
        host = os.getenv('POSTGRES_HOST', 'africaits.com')
        port = os.getenv('POSTGRES_PORT', '5432')
    else:
        # En local, utiliser localhost ou host.docker.internal
        host = os.getenv('POSTGRES_HOST', 'localhost')
        port = os.getenv('POSTGRES_PORT', '5433')
    
    database = os.getenv('POSTGRES_DB', 'Traffic_Tracking')
    user = os.getenv('POSTGRES_USER', 'Alidorsabue')
    password = os.getenv('POSTGRES_PASSWORD', 'Virgi@1996')
    
    # En production, vérifier que les credentials sont configurés
    if os.getenv('ENVIRONMENT') == 'production' and password in ['postgres', '']:
        raise ValueError("POSTGRES_PASSWORD doit être configuré en production !")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

DB_URI = get_db_uri()
engine = create_engine(DB_URI)

# Configuration Twilio (WhatsApp API)
# Utiliser des variables d'environnement pour la sécurité en production

# Configuration Twilio depuis les variables d'environnement
# En production, ces valeurs DOIVENT être définies
TWILIO_SID = os.getenv("TWILIO_SID", None)
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", None)
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

# Paramètres d'alerte depuis les variables d'environnement
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.6"))
DEBOUNCE_MIN = int(os.getenv("DEBOUNCE_MIN", "900"))

# Initialiser le client Twilio seulement si les credentials sont fournis et valides
# Vérifier que les credentials ne sont pas des placeholders
is_sid_valid = TWILIO_SID and TWILIO_SID.startswith("AC") and len(TWILIO_SID) > 20
is_token_valid = TWILIO_AUTH_TOKEN and TWILIO_AUTH_TOKEN and len(TWILIO_AUTH_TOKEN) > 10

# En production, vérifier que Twilio est configuré
if os.getenv('ENVIRONMENT') == 'production' and not (is_sid_valid and is_token_valid):
    raise ValueError("TWILIO_SID et TWILIO_AUTH_TOKEN doivent être configurés en production !")

if is_sid_valid and is_token_valid:
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        print("Client Twilio initialisé avec succès")
    except Exception as e:
        print(f"Erreur lors de l'initialisation du client Twilio: {e}")
        client = None
else:
    client = None
    print("Twilio non configuré - les alertes WhatsApp seront désactivées")

# Paramètres d'alerte
# ALERT_THRESHOLD: Seuil d'indice de congestion pour déclencher une alerte (0.0 à 1.0)
# - Indice de congestion = 1 - (vitesse_actuelle / vitesse_baseline)
# - Exemple: si vitesse = 20 km/h et baseline = 50 km/h → indice = 1 - (20/50) = 0.6 (60% de congestion)
# - Seuil par défaut: 0.6 signifie que l'alerte est envoyée si la vitesse est réduite de 60% ou plus
# - Valeur 0.0 = pas de congestion, 1.0 = arrêt total
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.6"))  # Index de congestion > 0.6 => alerte

# DEBOUNCE_MIN: Délai minimum entre deux alertes pour le même chauffeur (en secondes)
# - Empêche le spam d'alertes (par défaut: 15 minutes = 900 secondes)
# - Un chauffeur ne recevra pas plus d'une alerte toutes les 15 minutes
DEBOUNCE_MIN = int(os.getenv("DEBOUNCE_MIN", "900"))  # 15 minutes entre deux alertes (en secondes)

# Cache pour le réseau routier (pour éviter de le télécharger à chaque fois)
_cached_network_graph = None
_cached_network_nodes = None
_cached_network_place = None

# Fonctions utilitaires pour la localisation et les routes alternatives

def get_edge_coordinates(edge_u, edge_v):
    """
    Récupère les coordonnées GPS (latitude, longitude) d'un tronçon routier.
    
    Parameters:
    -----------
    edge_u : int
        Identifiant du nœud de départ
    edge_v : int
        Identifiant du nœud d'arrivée
    
    Returns:
    --------
    tuple or None
        (lat, lon) du point médian du tronçon, ou None si erreur
    """
    try:
        # Import lazy d'OSMnx
        import osmnx as ox
        
        # Configurer le cache OSMnx si pas déjà fait
        if not hasattr(ox.settings, '_cache_folder_configured'):
            # Détecter si on est dans Docker ou local
            if os.path.exists('/opt/airflow'):
                # Dans Docker (Airflow)
                cache_dir = '/opt/airflow/cache'
            else:
                # En local
                cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
            os.makedirs(cache_dir, exist_ok=True)
            ox.settings.cache_folder = cache_dir
            ox.settings.use_cache = True
            ox.settings._cache_folder_configured = True
        
        global _cached_network_graph, _cached_network_nodes, _cached_network_place
        
        place = "Kinshasa, Democratic Republic of the Congo"
        
        # Charger le réseau routier si nécessaire
        if _cached_network_graph is None or _cached_network_place != place:
            try:
                print(f"Chargement du réseau routier pour {place}...")
                G = ox.graph_from_place(place, network_type="drive")
                nodes, edges = ox.graph_to_gdfs(G)
                _cached_network_graph = G
                _cached_network_nodes = nodes
                _cached_network_place = place
            except Exception as e:
                print(f"Erreur lors du chargement du réseau routier: {e}")
                return None
        
        # Récupérer les coordonnées des nœuds
        if edge_u in _cached_network_nodes.index and edge_v in _cached_network_nodes.index:
            node_u = _cached_network_nodes.loc[edge_u]
            node_v = _cached_network_nodes.loc[edge_v]
            
            # Calculer le point médian
            lat = (node_u['y'] + node_v['y']) / 2
            lon = (node_u['x'] + node_v['x']) / 2
            
            return (lat, lon)
        else:
            print(f"Nœuds {edge_u} ou {edge_v} non trouvés dans le réseau")
            return None
            
    except Exception as e:
        print(f"Erreur lors de la récupération des coordonnées de l'edge ({edge_u}, {edge_v}): {e}")
        return None

def find_alternative_route(edge_u, edge_v, current_lat=None, current_lon=None):
    """
    Trouve une route alternative proche pour éviter l'embouteillage.
    
    Parameters:
    -----------
    edge_u : int
        Identifiant du nœud de départ du tronçon encombré
    edge_v : int
        Identifiant du nœud d'arrivée du tronçon encombré
    current_lat : float, optional
        Latitude actuelle du chauffeur (si disponible)
    current_lon : float, optional
        Longitude actuelle du chauffeur (si disponible)
    
    Returns:
    --------
    dict or None
        Dictionnaire avec 'name' (nom de la route), 'distance_km' (distance en km), 
        'direction' (direction générale), ou None si aucune alternative trouvée
    """
    try:
        # Import lazy d'OSMnx
        import osmnx as ox
        import networkx as nx
        
        # Configurer le cache OSMnx si pas déjà fait
        if not hasattr(ox.settings, '_cache_folder_configured'):
            # Détecter si on est dans Docker ou local
            if os.path.exists('/opt/airflow'):
                # Dans Docker (Airflow)
                cache_dir = '/opt/airflow/cache'
            else:
                # En local
                cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
            os.makedirs(cache_dir, exist_ok=True)
            ox.settings.cache_folder = cache_dir
            ox.settings.use_cache = True
            ox.settings._cache_folder_configured = True
        
        global _cached_network_graph, _cached_network_nodes
        
        if _cached_network_graph is None:
            return None
        
        # Essayer de trouver des routes parallèles ou alternatives
        # Chercher les nœuds voisins qui ne sont pas sur le tronçon encombré
        alternative_routes = []
        
        try:
            # Récupérer les voisins du nœud de départ
            if edge_u in _cached_network_graph:
                neighbors = list(_cached_network_graph.neighbors(edge_u))
                
                # Filtrer pour exclure le nœud d'arrivée actuel
                alternative_neighbors = [n for n in neighbors if n != edge_v]
                
                if alternative_neighbors:
                    # Prendre le premier voisin alternatif
                    alt_node = alternative_neighbors[0]
                    
                    # Récupérer le nom de la route si disponible
                    edge_data = _cached_network_graph.get_edge_data(edge_u, alt_node, 0)
                    route_name = edge_data.get('name', 'Route alternative') if edge_data else 'Route alternative'
                    
                    # Si c'est une liste, prendre le premier élément
                    if isinstance(route_name, list):
                        route_name = route_name[0] if route_name else 'Route alternative'
                    
                    # Calculer la direction approximative
                    if alt_node in _cached_network_nodes.index:
                        alt_coords = _cached_network_nodes.loc[alt_node]
                        if edge_u in _cached_network_nodes.index:
                            current_coords = _cached_network_nodes.loc[edge_u]
                            
                            # Calculer la direction cardinale approximative
                            lat_diff = alt_coords['y'] - current_coords['y']
                            lon_diff = alt_coords['x'] - current_coords['x']
                            
                            if abs(lat_diff) > abs(lon_diff):
                                direction = "Nord" if lat_diff > 0 else "Sud"
                            else:
                                direction = "Est" if lon_diff > 0 else "Ouest"
                            
                            return {
                                'name': route_name,
                                'direction': direction,
                                'distance_km': None  # Pas de calcul précis pour l'instant
                            }
                    
                    return {
                        'name': route_name,
                        'direction': None,
                        'distance_km': None
                    }
        except Exception as e:
            print(f"Erreur lors de la recherche de route alternative: {e}")
        
        return None
        
    except Exception as e:
        print(f"Erreur lors de la recherche d'une route alternative: {e}")
        return None

def format_location_message(lat, lon):
    """
    Formate un message de localisation lisible.
    
    Parameters:
    -----------
    lat : float
        Latitude
    lon : float
        Longitude
    
    Returns:
    --------
    str
        Message de localisation formaté
    """
    if lat is None or lon is None:
        return "Localisation non disponible"
    
    # Arrondir à 4 décimales (précision ~11 mètres)
    lat_rounded = round(lat, 4)
    lon_rounded = round(lon, 4)
    
    return f"Coordonnées: {lat_rounded}, {lon_rounded}"

def create_alert_message(congestion_index, edge_u=None, edge_v=None, driver_lat=None, driver_lon=None):
    """
    Crée un message d'alerte enrichi avec localisation et route alternative.
    
    Parameters:
    -----------
    congestion_index : float
        Indice de congestion (0.0 à 1.0)
        - Formule: 1 - (vitesse_actuelle / vitesse_baseline)
        - 0.0 = pas de congestion (vitesse normale)
        - 1.0 = congestion totale (arrêt, vitesse = 0)
        - Exemple: 0.6 = vitesse réduite de 60% (si baseline=50km/h et vitesse=20km/h)
    edge_u : int, optional
        Identifiant du nœud de départ du tronçon
    edge_v : int, optional
        Identifiant du nœud d'arrivée du tronçon
    driver_lat : float, optional
        Latitude actuelle du chauffeur
    driver_lon : float, optional
        Longitude actuelle du chauffeur
    
    Returns:
    --------
    str
        Message d'alerte formaté
    """
    # Message de base avec explication de l'indice de congestion
    # Convertir l'indice en pourcentage lisible
    congestion_percent = int(congestion_index * 100)
    
    message_parts = [
        "EMBOUTEILLAGE DETECTE",
        f"Indice de congestion: {congestion_percent}%",
        f"(Vitesse reduite de {congestion_percent}% par rapport a la normale)",
        ""
    ]
    
    # Ajouter la localisation
    if edge_u is not None and edge_v is not None:
        edge_coords = get_edge_coordinates(edge_u, edge_v)
        if edge_coords:
            lat, lon = edge_coords
            message_parts.append(f"Localisation: {format_location_message(lat, lon)}")
        else:
            message_parts.append("Localisation: Zone de congestion detectee")
    elif driver_lat is not None and driver_lon is not None:
        message_parts.append(f"Votre position: {format_location_message(driver_lat, driver_lon)}")
    
    # Ajouter une route alternative si disponible
    if edge_u is not None and edge_v is not None:
        alt_route = find_alternative_route(edge_u, edge_v, driver_lat, driver_lon)
        if alt_route:
            route_info = f"Route alternative: {alt_route['name']}"
            if alt_route.get('direction'):
                route_info += f" (direction {alt_route['direction']})"
            message_parts.append(route_info)
        else:
            message_parts.append("Suggestion: Consultez votre GPS pour une route alternative")
    else:
        message_parts.append("Suggestion: Consultez votre GPS pour une route alternative")
    
    message_parts.append("")
    message_parts.append("Ralentissement sur votre trajet.")
    
    return "\n".join(message_parts)

# Fonctions utilitaires

def fetch_current_congestion():
    """
    Récupère les vitesses moyennes par tronçon avec leur baseline.
    Utilise une jointure avec edge_hourly_baseline pour calculer l'indice de congestion.
    
    Returns:
    --------
    pd.DataFrame
        DataFrame avec les colonnes: edge_u, edge_v, avg_speed_kmh, baseline_kmh, congestion_index, ts
        Retourne un DataFrame vide en cas d'erreur
        
    Raises:
    -------
    Exception
        Si une erreur critique survient
    """
    try:
        # Vérifier si la table edge_hourly_baseline existe
        check_table_sql = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'edge_hourly_baseline'
        );
        """
        table_exists = pd.read_sql(check_table_sql, engine).iloc[0, 0]
        
        if table_exists:
            # Requête avec jointure sur edge_hourly_baseline
            sql = """
            WITH latest_agg AS (
                SELECT DISTINCT ON (edge_u, edge_v)
                    edge_u, edge_v, avg_speed_kmh, ts
                FROM edge_agg
                ORDER BY edge_u, edge_v, ts DESC
            )
            SELECT 
                la.edge_u, 
                la.edge_v, 
                la.avg_speed_kmh,
                COALESCE(b.baseline_kmh, 50.0) as baseline_kmh,
                (1 - (la.avg_speed_kmh / NULLIF(COALESCE(b.baseline_kmh, 50.0), 0))) as congestion_index,
                la.ts
            FROM latest_agg la
            LEFT JOIN edge_hourly_baseline b 
                ON la.edge_u = b.edge_u 
                AND la.edge_v = b.edge_v 
                AND EXTRACT(HOUR FROM la.ts) = b.hour
            WHERE la.avg_speed_kmh IS NOT NULL;
            """
        else:
            # Requête simplifiée sans baseline (utilise 50 km/h comme valeur par défaut)
            print("Table edge_hourly_baseline non trouvée, utilisation de la valeur par défaut (50 km/h)")
            sql = """
            WITH latest_agg AS (
                SELECT DISTINCT ON (edge_u, edge_v)
                    edge_u, edge_v, avg_speed_kmh, ts
                FROM edge_agg
                ORDER BY edge_u, edge_v, ts DESC
            )
            SELECT 
                la.edge_u, 
                la.edge_v, 
                la.avg_speed_kmh,
                50.0 as baseline_kmh,
                (1 - (la.avg_speed_kmh / 50.0)) as congestion_index,
                la.ts
            FROM latest_agg la
            WHERE la.avg_speed_kmh IS NOT NULL;
            """
        
        df = pd.read_sql(sql, engine)
        if df.empty:
            print("Aucune donnée de congestion trouvée dans edge_agg")
        else:
            print(f"Récupération de {len(df)} tronçons avec données de congestion")
        return df
    except Exception as e:
        print(f"Erreur lors de la récupération des données de congestion: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def fetch_drivers_on_edge(edge_u, edge_v):
    """
    Récupère les chauffeurs actuellement sur un tronçon donné.
    
    Parameters:
    -----------
    edge_u : int
        Identifiant du nœud de départ du tronçon
    edge_v : int
        Identifiant du nœud d'arrivée du tronçon
    
    Returns:
    --------
    pd.DataFrame
        DataFrame avec les colonnes: driver_id, phone_number, last_alert_at, current_lat, current_lon
        Retourne un DataFrame vide en cas d'erreur ou si aucun chauffeur n'est trouvé
    """
    conn = None
    try:
        # Validation des paramètres
        edge_u = int(edge_u)
        edge_v = int(edge_v)
        
        conn = get_db_connection()
        # Récupérer aussi les coordonnées GPS si disponibles
        sql = """
          SELECT driver_id, phone_number, last_alert_at, 
                 current_latitude as current_lat, current_longitude as current_lon
          FROM drivers_registry
          WHERE current_edge_u = %s
            AND current_edge_v = %s
            AND notifications_enabled = true;
        """
        df = pd.read_sql(sql, conn, params=(edge_u, edge_v))
        return df
    except (ValueError, TypeError) as e:
        print(f"Erreur de validation des paramètres edge_u/edge_v: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Erreur lors de la récupération des chauffeurs pour edge ({edge_u}, {edge_v}): {e}")
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception as e:
                print(f"Erreur lors de la fermeture de la connexion: {e}")

def send_whatsapp(phone_number, message):
    """
    Envoie un message WhatsApp via Twilio.
    
    Parameters:
    -----------
    phone_number : str
        Numéro de téléphone du destinataire (format international sans +)
    message : str
        Message à envoyer
    
    Returns:
    --------
    str or None
        ID du message Twilio si l'envoi réussit, None sinon
    """
    if client is None:
        print(f"Twilio non configuré - message simulé pour {phone_number}: {message}")
        return None
    
    # Validation du numéro de téléphone
    if not phone_number or not isinstance(phone_number, str):
        print(f"Numéro de téléphone invalide: {phone_number}")
        return None
    
    # Validation du message
    if not message or not isinstance(message, str):
        print(f"Message invalide: {message}")
        return None
    
    try:
        # Nettoyer le numéro de téléphone (enlever les caractères non numériques sauf +)
        clean_phone = phone_number.strip()
        if not clean_phone.startswith('+'):
            clean_phone = '+' + clean_phone
        
        msg = client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{clean_phone}"
        )
        print(f"Message envoyé à {clean_phone} (SID: {msg.sid})")
        return msg.sid
    except Exception as e:
        print(f"Erreur lors de l'envoi WhatsApp à {phone_number}: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_alerts():
    """
    Analyse les congestions et envoie des alertes WhatsApp aux chauffeurs concernés.
    Cette fonction peut être appelée directement depuis Airflow.
    
    **TIMING ET DISTANCES DE DÉTECTION:**
    - Fréquence d'exécution: Le DAG Airflow s'exécute toutes les 10 minutes (schedule_interval='*/10 * * * *')
    - Détection: Les embouteillages sont détectés sur des tronçons routiers (edges) de longueur variable
      - Distance de map matching: 50 mètres (max_distance=50) - les points GPS sont associés aux routes dans un rayon de 50m
      - Agrégation temporelle: Les vitesses sont agrégées par tronçon toutes les 10 minutes
      - Longueur des tronçons: Variable selon le réseau routier OSM (généralement entre 50m et 500m)
    - Délai d'envoi: Maximum 10 minutes après la détection (durée d'un cycle du DAG)
    - Protection anti-spam: Un chauffeur ne reçoit pas plus d'une alerte toutes les 15 minutes (DEBOUNCE_MIN)
    
    **INDICE DE CONGESTION:**
    - Formule: 1 - (vitesse_actuelle / vitesse_baseline)
    - Exemples:
      * Vitesse normale (50 km/h) / Baseline (50 km/h) → indice = 0.0 (pas de congestion)
      * Vitesse réduite (20 km/h) / Baseline (50 km/h) → indice = 0.6 (60% de congestion)
      * Arrêt total (0 km/h) / Baseline (50 km/h) → indice = 1.0 (congestion totale)
    - Seuil d'alerte: Par défaut 0.6 (60% de réduction de vitesse)
    
    Returns:
    --------
    dict
        Dictionnaire avec le nombre d'alertes envoyées et le statut
    """
    alerts_sent = 0
    errors_count = 0
    
    try:
        # Récupérer les données de congestion
        congestions = fetch_current_congestion()
        
        if congestions.empty:
            print("Aucune donnée de congestion disponible")
            return {"alerts_envoyées": 0, "statut": "aucune_donnée"}
        
        print(f"Analyse de {len(congestions)} tronçons pour détecter les congestions")
        
        # Parcourir chaque tronçon avec congestion
        for idx, row in congestions.iterrows():
            try:
                # Validation et extraction des données
                ci = float(row.get('congestion_index', 0.0) or 0.0)
                edge_u = row.get('edge_u')
                edge_v = row.get('edge_v')
                
                # Validation des données
                if pd.isna(edge_u) or pd.isna(edge_v):
                    print(f"Tronçon avec edge_u ou edge_v manquant ignoré (index: {idx})")
                    continue
                
                if ci > ALERT_THRESHOLD:
                    print(f"Congestion détectée sur edge ({edge_u}, {edge_v}): indice {ci:.2f}")
                    
                    # Récupérer les chauffeurs sur ce tronçon
                    drivers = fetch_drivers_on_edge(int(edge_u), int(edge_v))
                    
                    if drivers.empty:
                        continue
                    
                    print(f"  {len(drivers)} chauffeur(s) trouvé(s) sur ce tronçon")
                    
                    # Traiter chaque chauffeur
                    for _, d in drivers.iterrows():
                        try:
                            now_ts = int(time.time())
                            last_alert = d.get('last_alert_at')
                            phone_number = d.get('phone_number')
                            driver_id = d.get('driver_id')
                            
                            # Validation des données du chauffeur
                            if pd.isna(phone_number) or not phone_number:
                                print(f"  Chauffeur {driver_id}: numéro de téléphone manquant, ignoré")
                                continue
                            
                            # Vérifier le debounce (15 minutes entre deux alertes)
                            should_alert = False
                            if pd.isna(last_alert):
                                should_alert = True
                            else:
                                # Convertir last_alert_at en timestamp si nécessaire
                                if isinstance(last_alert, pd.Timestamp):
                                    last_alert_ts = int(last_alert.timestamp())
                                else:
                                    try:
                                        last_alert_ts = int(last_alert)
                                    except (ValueError, TypeError):
                                        should_alert = True
                                
                                if not should_alert:
                                    if (now_ts - last_alert_ts) > DEBOUNCE_MIN:
                                        should_alert = True
                            
                            if should_alert:
                                # Récupérer les coordonnées GPS du chauffeur si disponibles
                                driver_lat = d.get('current_lat')
                                driver_lon = d.get('current_lon')
                                
                                # Créer le message enrichi avec localisation et route alternative
                                message = create_alert_message(
                                    congestion_index=ci,
                                    edge_u=int(edge_u),
                                    edge_v=int(edge_v),
                                    driver_lat=driver_lat if not pd.isna(driver_lat) else None,
                                    driver_lon=driver_lon if not pd.isna(driver_lon) else None
                                )
                                
                                # Envoyer le message WhatsApp
                                msg_sid = send_whatsapp(phone_number, message)
                                
                                # Mettre à jour le timestamp de dernière alerte seulement si l'envoi a réussi
                                if msg_sid is not None:
                                    conn = None
                                    cursor = None
                                    try:
                                        conn = get_db_connection()
                                        cursor = conn.cursor()
                                        cursor.execute(
                                            """
                                            UPDATE drivers_registry
                                            SET last_alert_at = to_timestamp(%s)
                                            WHERE driver_id = %s
                                            """,
                                            (now_ts, str(driver_id))
                                        )
                                        conn.commit()
                                        alerts_sent += 1
                                        print(f"  Alerte envoyée au chauffeur {driver_id} ({phone_number})")
                                    except Exception as e:
                                        print(f"  Erreur lors de la mise à jour de last_alert_at pour le chauffeur {driver_id}: {e}")
                                        errors_count += 1
                                        if conn:
                                            conn.rollback()
                                    finally:
                                        if cursor:
                                            cursor.close()
                                        if conn:
                                            conn.close()
                                else:
                                    print(f"  Échec de l'envoi WhatsApp au chauffeur {driver_id}, pas de mise à jour de last_alert_at")
                                    errors_count += 1
                            else:
                                print(f"  Chauffeur {driver_id}: alerte récente, debounce actif")
                        except Exception as e:
                            print(f"  Erreur lors du traitement du chauffeur: {e}")
                            errors_count += 1
                            continue
            except Exception as e:
                print(f"Erreur lors du traitement du tronçon (index {idx}): {e}")
                errors_count += 1
                continue
        
        result = {
            "alerts_envoyées": alerts_sent,
            "erreurs": errors_count,
            "statut": "succès" if errors_count == 0 else "succès_avec_erreurs"
        }
        print(f"Résumé: {alerts_sent} alertes envoyées, {errors_count} erreur(s)")
        return result
        
    except Exception as e:
        error_msg = f"Erreur critique lors de l'exécution des alertes: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {"alerts_envoyées": alerts_sent, "erreurs": errors_count, "statut": "erreur", "message": str(e)}

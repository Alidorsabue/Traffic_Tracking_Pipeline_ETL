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
DEBOUNCE_MIN = int(os.getenv("DEBOUNCE_MIN", "900"))  # 15 minutes entre deux alertes si changement de route (en secondes)

# DEBOUNCE_MIN_SAME_ROUTE: Délai minimum entre deux alertes pour le même chauffeur sur la même route (en secondes)
# - Délai plus long si le chauffeur est toujours sur la même route (par défaut: 20 minutes = 1200 secondes)
# - Empêche le spam d'alertes répétées pour la même congestion
DEBOUNCE_MIN_SAME_ROUTE = int(os.getenv("DEBOUNCE_MIN_SAME_ROUTE", "1200"))  # 20 minutes si même route (en secondes)

# Paramètres pour les alertes anticipées (proactives)
# ALERT_PREDICT_DISTANCE_MAX: Distance maximale avant l'embouteillage pour envoyer une alerte (en mètres)
# - Alerte envoyée si la congestion est à moins de cette distance sur la route prédite
# - Valeur par défaut: 2000 mètres (2 km)
ALERT_PREDICT_DISTANCE_MAX = float(os.getenv("ALERT_PREDICT_DISTANCE_MAX", "2000"))  # 2 km

# ALERT_PREDICT_TIME_MAX: Temps maximum avant l'arrivée à l'embouteillage pour envoyer une alerte (en secondes)
# - Alerte envoyée si le chauffeur arrive dans moins de ce temps à l'embouteillage
# - Valeur par défaut: 300 secondes (5 minutes)
ALERT_PREDICT_TIME_MAX = int(os.getenv("ALERT_PREDICT_TIME_MAX", "300"))  # 5 minutes

# ALERT_PREDICT_ROUTE_LENGTH: Longueur de la route à prédire (en mètres)
# - Distance maximale à parcourir pour prédire la route future
# - Valeur par défaut: 5000 mètres (5 km)
ALERT_PREDICT_ROUTE_LENGTH = float(os.getenv("ALERT_PREDICT_ROUTE_LENGTH", "5000"))  # 5 km

# ALERT_PREDICT_MIN_POSITIONS: Nombre minimum de positions GPS pour prédire la route
# - Nécessite au moins ce nombre de positions récentes pour estimer la direction
# - Valeur par défaut: 3 positions
ALERT_PREDICT_MIN_POSITIONS = int(os.getenv("ALERT_PREDICT_MIN_POSITIONS", "3"))

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

def fetch_driver_recent_positions(driver_id, minutes=10, limit=10):
    """
    Récupère les dernières positions GPS d'un chauffeur pour prédire sa route.
    
    Parameters:
    -----------
    driver_id : str
        Identifiant du chauffeur
    minutes : int
        Nombre de minutes dans le passé pour récupérer les positions (défaut: 10)
    limit : int
        Nombre maximum de positions à récupérer (défaut: 10)
    
    Returns:
    --------
    pd.DataFrame
        DataFrame avec les colonnes: latitude, longitude, speed, timestamp
        Trié par timestamp décroissant (plus récent en premier)
        Retourne un DataFrame vide si aucune position trouvée
    """
    conn = None
    try:
        conn = get_db_connection()
        sql = """
            SELECT latitude, longitude, speed, timestamp
            FROM gps_points
            WHERE driver_id = %s
              AND timestamp >= NOW() - INTERVAL '%s minutes'
            ORDER BY timestamp DESC
            LIMIT %s
        """
        df = pd.read_sql(sql, conn, params=(str(driver_id), minutes, limit))
        return df
    except Exception as e:
        print(f"Erreur lors de la récupération des positions GPS pour le chauffeur {driver_id}: {e}")
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

def predict_driver_route(driver_id, current_lat, current_lon, current_speed=None):
    """
    Prédit la route future d'un chauffeur en analysant ses dernières positions GPS
    et en utilisant un algorithme de routage.
    
    Parameters:
    -----------
    driver_id : str
        Identifiant du chauffeur
    current_lat : float
        Latitude actuelle du chauffeur
    current_lon : float
        Longitude actuelle du chauffeur
    current_speed : float, optional
        Vitesse actuelle du chauffeur (en km/h)
    
    Returns:
    --------
    list or None
        Liste de tuples (edge_u, edge_v) représentant la route prédite,
        ou None si la prédiction échoue
    """
    try:
        import osmnx as ox
        import networkx as nx
        from math import radians, cos, sin, asin, sqrt
        
        # Configurer OSMnx
        if not hasattr(ox.settings, '_cache_folder_configured'):
            if os.path.exists('/opt/airflow'):
                cache_dir = '/opt/airflow/cache'
            else:
                cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
            os.makedirs(cache_dir, exist_ok=True)
            ox.settings.cache_folder = cache_dir
            ox.settings.use_cache = True
            ox.settings._cache_folder_configured = True
        
        global _cached_network_graph, _cached_network_nodes
        
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
        
        if _cached_network_graph is None:
            return None
        
        # Fonction pour calculer la distance haversine (mètres)
        def haversine_distance(lat1, lon1, lat2, lon2):
            R = 6371000  # Rayon de la Terre en mètres
            phi1 = radians(lat1)
            phi2 = radians(lat2)
            dphi = radians(lat2 - lat1)
            dlambda = radians(lon2 - lon1)
            a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
            c = 2 * asin(sqrt(a))
            return R * c
        
        # Trouver le nœud le plus proche de la position actuelle
        current_node = ox.distance.nearest_nodes(_cached_network_graph, current_lon, current_lat)
        
        # Récupérer les dernières positions pour estimer la direction
        recent_positions = fetch_driver_recent_positions(driver_id, minutes=10, limit=ALERT_PREDICT_MIN_POSITIONS)
        
        if len(recent_positions) < ALERT_PREDICT_MIN_POSITIONS:
            # Pas assez de données pour prédire la direction, utiliser la route la plus courte
            # On cherche les nœuds voisins pour continuer dans la direction générale
            predicted_route = []
            
            # Utiliser les voisins du nœud actuel comme route prédite (direction générale)
            if current_node in _cached_network_graph:
                neighbors = list(_cached_network_graph.neighbors(current_node))
                if neighbors:
                    # Prendre les 3 premiers voisins (routes principales probables)
                    for neighbor in neighbors[:3]:
                        if len(predicted_route) < 10:  # Limiter à 10 tronçons
                            predicted_route.append((current_node, neighbor))
            
            return predicted_route if predicted_route else None
        
        # Calculer la direction moyenne à partir des dernières positions
        recent_positions = recent_positions.sort_values('timestamp')
        
        # Calculer le point de départ estimé (2ème position)
        start_lat = recent_positions.iloc[0]['latitude']
        start_lon = recent_positions.iloc[0]['longitude']
        
        # Calculer le vecteur directionnel moyen
        lat_diff = current_lat - start_lat
        lon_diff = current_lon - start_lon
        
        # Estimer la destination probable (continuer dans la même direction)
        # Projeter sur une distance de ALERT_PREDICT_ROUTE_LENGTH
        distance_km = haversine_distance(start_lat, start_lon, current_lat, current_lon) / 1000
        
        if distance_km < 0.01:  # Moins de 10 mètres de mouvement
            return None
        
        # Normaliser le vecteur directionnel
        scale = (ALERT_PREDICT_ROUTE_LENGTH / 1000) / distance_km  # Conversion en km
        estimated_dest_lat = current_lat + (lat_diff * scale)
        estimated_dest_lon = current_lon + (lon_diff * scale)
        
        # Trouver le nœud de destination estimé
        try:
            dest_node = ox.distance.nearest_nodes(_cached_network_graph, estimated_dest_lon, estimated_dest_lat)
        except Exception:
            return None
        
        # Calculer le plus court chemin (route probable)
        try:
            route_nodes = nx.shortest_path(_cached_network_graph, current_node, dest_node, weight='length')
        except nx.NetworkXNoPath:
            # Pas de chemin trouvé, retourner les tronçons voisins
            route_nodes = [current_node]
            if current_node in _cached_network_graph:
                neighbors = list(_cached_network_graph.neighbors(current_node))
                if neighbors:
                    route_nodes.append(neighbors[0])
        
        # Convertir les nœuds en tronçons (edges)
        predicted_route = []
        for i in range(len(route_nodes) - 1):
            edge_u = route_nodes[i]
            edge_v = route_nodes[i + 1]
            predicted_route.append((edge_u, edge_v))
        
        return predicted_route if predicted_route else None
        
    except Exception as e:
        print(f"Erreur lors de la prédiction de route pour le chauffeur {driver_id}: {e}")
        import traceback
        traceback.print_exc()
        return None

def calculate_distance_to_congestion(predicted_route, congestions_dict, current_edge_u=None, current_edge_v=None):
    """
    Calcule la distance jusqu'à la première congestion sur la route prédite.
    
    Parameters:
    -----------
    predicted_route : list
        Liste de tuples (edge_u, edge_v) représentant la route prédite
    congestions_dict : dict
        Dictionnaire avec clés (edge_u, edge_v) et valeurs (congestion_index, avg_speed_kmh, baseline_kmh)
    current_edge_u : int, optional
        Tronçon actuel du chauffeur (pour ignorer dans le calcul)
    current_edge_v : int, optional
        Tronçon actuel du chauffeur (pour ignorer dans le calcul)
    
    Returns:
    --------
    dict or None
        Dictionnaire avec 'distance_m' (distance en mètres), 'congestion_index', 
        'edge_u', 'edge_v', 'estimated_time_s' (temps estimé en secondes)
        ou None si aucune congestion trouvée sur la route
    """
    try:
        import osmnx as ox
        from math import radians, cos, sin, asin, sqrt
        
        if not predicted_route:
            return None
        
        # Fonction pour calculer la longueur d'un tronçon (mètres)
        def get_edge_length(edge_u, edge_v):
            try:
                global _cached_network_graph
                if _cached_network_graph is None:
                    return 0
                
                edge_data = _cached_network_graph.get_edge_data(edge_u, edge_v, 0)
                if edge_data and 'length' in edge_data:
                    return edge_data['length']
                
                # Si pas de longueur, estimer à partir des coordonnées des nœuds
                global _cached_network_nodes
                if _cached_network_nodes is not None:
                    if edge_u in _cached_network_nodes.index and edge_v in _cached_network_nodes.index:
                        node_u = _cached_network_nodes.loc[edge_u]
                        node_v = _cached_network_nodes.loc[edge_v]
                        
                        # Distance haversine
                        R = 6371000
                        phi1 = radians(node_u['y'])
                        phi2 = radians(node_v['y'])
                        dphi = radians(node_v['y'] - node_u['y'])
                        dlambda = radians(node_v['x'] - node_u['x'])
                        a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
                        c = 2 * asin(sqrt(a))
                        return R * c
                
                return 100  # Longueur par défaut estimée (100 m)
            except Exception:
                return 100
        
        total_distance = 0
        
        # Parcourir la route prédite
        for edge_u, edge_v in predicted_route:
            # Ignorer le tronçon actuel si spécifié
            if current_edge_u is not None and current_edge_v is not None:
                if edge_u == current_edge_u and edge_v == current_edge_v:
                    continue
            
            # Vérifier si ce tronçon a une congestion
            edge_key = (int(edge_u), int(edge_v))
            
            if edge_key in congestions_dict:
                congestion_info = congestions_dict[edge_key]
                congestion_index = congestion_info.get('congestion_index', 0)
                
                # Vérifier si la congestion dépasse le seuil
                if congestion_index >= ALERT_THRESHOLD:
                    return {
                        'distance_m': total_distance,
                        'congestion_index': congestion_index,
                        'edge_u': edge_u,
                        'edge_v': edge_v,
                        'avg_speed_kmh': congestion_info.get('avg_speed_kmh', 0),
                        'baseline_kmh': congestion_info.get('baseline_kmh', 50),
                        'estimated_time_s': None  # Sera calculé avec la vitesse du chauffeur
                    }
            
            # Ajouter la longueur de ce tronçon à la distance totale
            edge_length = get_edge_length(edge_u, edge_v)
            total_distance += edge_length
            
            # Limiter à ALERT_PREDICT_ROUTE_LENGTH
            if total_distance > ALERT_PREDICT_ROUTE_LENGTH:
                break
        
        return None  # Aucune congestion trouvée sur la route
        
    except Exception as e:
        print(f"Erreur lors du calcul de la distance jusqu'à la congestion: {e}")
        import traceback
        traceback.print_exc()
        return None

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

def fetch_all_active_drivers(minutes=15):
    """
    Récupère tous les chauffeurs actifs avec leurs dernières positions GPS.
    
    Parameters:
    -----------
    minutes : int
        Nombre de minutes dans le passé pour considérer un chauffeur comme actif (défaut: 15)
    
    Returns:
    --------
    pd.DataFrame
        DataFrame avec les colonnes: driver_id, phone_number, last_alert_at, 
        current_lat, current_lon, current_edge_u, current_edge_v, current_speed
        Retourne un DataFrame vide en cas d'erreur
    """
    conn = None
    try:
        conn = get_db_connection()
        # Créer les colonnes last_alert_edge_u et last_alert_edge_v si elles n'existent pas
        try:
            cursor = conn.cursor()
            cursor.execute("""
                ALTER TABLE drivers_registry 
                ADD COLUMN IF NOT EXISTS last_alert_edge_u BIGINT;
            """)
            cursor.execute("""
                ALTER TABLE drivers_registry 
                ADD COLUMN IF NOT EXISTS last_alert_edge_v BIGINT;
            """)
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"Note: Colonnes last_alert_edge_u/v déjà existantes ou erreur: {e}")
            if conn:
                conn.rollback()
        
        sql = f"""
            SELECT DISTINCT ON (d.driver_id)
                d.driver_id,
                d.phone_number,
                d.last_alert_at,
                d.last_alert_edge_u,
                d.last_alert_edge_v,
                g.latitude as current_lat,
                g.longitude as current_lon,
                d.current_edge_u,
                d.current_edge_v,
                g.speed as current_speed
            FROM drivers_registry d
            INNER JOIN LATERAL (
                SELECT latitude, longitude, speed, timestamp
                FROM gps_points
                WHERE driver_id = d.driver_id
                  AND timestamp >= NOW() - INTERVAL '{minutes} minutes'
                ORDER BY timestamp DESC
                LIMIT 1
            ) g ON true
            WHERE d.notifications_enabled = true
              AND EXISTS (
                  SELECT 1
                  FROM gps_points gp
                  WHERE gp.driver_id = d.driver_id
                    AND gp.timestamp >= NOW() - INTERVAL '{minutes} minutes'
              )
            ORDER BY d.driver_id, g.timestamp DESC
        """
        df = pd.read_sql(sql, conn)
        return df
    except Exception as e:
        print(f"Erreur lors de la récupération des chauffeurs actifs: {e}")
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

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
    Cette fonction utilise une approche PROACTIVE: elle prédit la route des chauffeurs
    et les alerte AVANT qu'ils n'atteignent une congestion.
    
    **TIMING ET DISTANCES DE DÉTECTION:**
    - Fréquence d'exécution: Le DAG Airflow s'exécute toutes les 10 minutes (schedule_interval='*/10 * * * *')
    - Approche proactive: Prédiction de route (2-5 km) + détection anticipée des congestions
    - Distance d'alerte: Chauffeur alerté si congestion à moins de ALERT_PREDICT_DISTANCE_MAX (2 km par défaut)
    - Temps d'alerte: Chauffeur alerté si arrivée estimée < ALERT_PREDICT_TIME_MAX (5 minutes par défaut)
    - Protection anti-spam contextuelle:
      * Si le chauffeur est sur la même route que la dernière alerte : 20 minutes (DEBOUNCE_MIN_SAME_ROUTE)
      * Si le chauffeur a changé de route : 15 minutes (DEBOUNCE_MIN)
    
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
        # Récupérer les données de congestion (convertir en dictionnaire pour accès rapide)
        congestions_df = fetch_current_congestion()
        
        if congestions_df.empty:
            print("Aucune donnée de congestion disponible")
            return {"alerts_envoyées": 0, "statut": "aucune_donnée"}
        
        # Convertir en dictionnaire pour accès rapide par (edge_u, edge_v)
        congestions_dict = {}
        for idx, row in congestions_df.iterrows():
            edge_u = row.get('edge_u')
            edge_v = row.get('edge_v')
            if not pd.isna(edge_u) and not pd.isna(edge_v):
                key = (int(edge_u), int(edge_v))
                congestions_dict[key] = {
                    'congestion_index': float(row.get('congestion_index', 0.0) or 0.0),
                    'avg_speed_kmh': float(row.get('avg_speed_kmh', 0) or 0),
                    'baseline_kmh': float(row.get('baseline_kmh', 50) or 50)
                }
        
        print(f"Analyse de {len(congestions_dict)} tronçons avec congestion détectée")
        
        # Récupérer tous les chauffeurs actifs
        active_drivers = fetch_all_active_drivers(minutes=15)
        
        if active_drivers.empty:
            print("Aucun chauffeur actif trouvé")
            return {"alerts_envoyées": 0, "statut": "aucun_chauffeur_actif"}
        
        print(f"Analyse de {len(active_drivers)} chauffeur(s) actif(s) pour alertes anticipées")
        
        # Traiter chaque chauffeur
        for _, driver in active_drivers.iterrows():
            try:
                driver_id = driver.get('driver_id')
                phone_number = driver.get('phone_number')
                current_lat = driver.get('current_lat')
                current_lon = driver.get('current_lon')
                current_edge_u = driver.get('current_edge_u')
                current_edge_v = driver.get('current_edge_v')
                current_speed = driver.get('current_speed')
                last_alert = driver.get('last_alert_at')
                last_alert_edge_u = driver.get('last_alert_edge_u')
                last_alert_edge_v = driver.get('last_alert_edge_v')
                
                # Validation des données du chauffeur
                if pd.isna(phone_number) or not phone_number:
                    print(f"Chauffeur {driver_id}: numéro de téléphone manquant, ignoré")
                    continue
                
                if pd.isna(current_lat) or pd.isna(current_lon):
                    print(f"Chauffeur {driver_id}: coordonnées GPS manquantes, ignoré")
                    continue
                
                # Prédire la route du chauffeur
                predicted_route = predict_driver_route(
                    driver_id=driver_id,
                    current_lat=float(current_lat),
                    current_lon=float(current_lon),
                    current_speed=float(current_speed) if not pd.isna(current_speed) else None
                )
                
                if not predicted_route:
                    print(f"Chauffeur {driver_id}: impossible de prédire la route")
                    continue
                
                # Calculer la distance jusqu'à la première congestion sur la route prédite
                congestion_info = calculate_distance_to_congestion(
                    predicted_route=predicted_route,
                    congestions_dict=congestions_dict,
                    current_edge_u=int(current_edge_u) if not pd.isna(current_edge_u) else None,
                    current_edge_v=int(current_edge_v) if not pd.isna(current_edge_v) else None
                )
                
                if congestion_info is None:
                    # Aucune congestion sur la route prédite
                    continue
                
                distance_m = congestion_info['distance_m']
                congestion_index = congestion_info['congestion_index']
                edge_u = congestion_info['edge_u']
                edge_v = congestion_info['edge_v']
                
                # Vérifier le debounce contextuel selon la route
                # Si le chauffeur est sur la même route que la dernière alerte : 20 minutes
                # Si le chauffeur a changé de route : 15 minutes
                should_alert = False
                now_ts = int(time.time())
                
                if pd.isna(last_alert):
                    should_alert = True
                else:
                    if isinstance(last_alert, pd.Timestamp):
                        last_alert_ts = int(last_alert.timestamp())
                    else:
                        try:
                            last_alert_ts = int(last_alert)
                        except (ValueError, TypeError):
                            should_alert = True
                    
                    if not should_alert:
                        # Vérifier si c'est la même route que la dernière alerte
                        is_same_route = False
                        if not pd.isna(last_alert_edge_u) and not pd.isna(last_alert_edge_v):
                            if int(last_alert_edge_u) == int(edge_u) and int(last_alert_edge_v) == int(edge_v):
                                is_same_route = True
                        
                        # Utiliser le debounce approprié selon la route
                        if is_same_route:
                            debounce_time = DEBOUNCE_MIN_SAME_ROUTE
                            if (now_ts - last_alert_ts) > debounce_time:
                                should_alert = True
                            else:
                                print(f"Chauffeur {driver_id}: alerte récente sur la même route, debounce actif (20 min)")
                        else:
                            debounce_time = DEBOUNCE_MIN
                            if (now_ts - last_alert_ts) > debounce_time:
                                should_alert = True
                            else:
                                print(f"Chauffeur {driver_id}: alerte récente (changement de route), debounce actif (15 min)")
                
                if not should_alert:
                    continue
                
                # Calculer le temps estimé d'arrivée à la congestion (en secondes)
                if not pd.isna(current_speed) and current_speed > 0:
                    speed_ms = (current_speed / 3.6)  # Conversion km/h -> m/s
                    estimated_time_s = distance_m / speed_ms if speed_ms > 0 else None
                else:
                    # Vitesse par défaut si inconnue (30 km/h = 8.33 m/s)
                    estimated_time_s = distance_m / 8.33
                
                congestion_info['estimated_time_s'] = estimated_time_s
                
                # Vérifier si on doit alerter (distance et temps)
                should_alert_proactive = False
                
                if distance_m <= ALERT_PREDICT_DISTANCE_MAX:
                    if estimated_time_s is not None and estimated_time_s <= ALERT_PREDICT_TIME_MAX:
                        should_alert_proactive = True
                    elif estimated_time_s is None:
                        # Si on ne peut pas calculer le temps, alerter uniquement si distance < 1 km
                        if distance_m <= 1000:
                            should_alert_proactive = True
                
                if should_alert_proactive:
                    print(f"Chauffeur {driver_id}: congestion détectée à {distance_m:.0f}m ({distance_m/1000:.2f}km)")
                    print(f"  Temps estimé: {estimated_time_s:.0f}s ({estimated_time_s/60:.1f}min)")
                    print(f"  Indice de congestion: {congestion_index:.2f}")
                    
                    # Créer le message enrichi
                    message = create_alert_message(
                        congestion_index=congestion_index,
                        edge_u=edge_u,
                        edge_v=edge_v,
                        driver_lat=float(current_lat),
                        driver_lon=float(current_lon)
                    )
                    
                    # Ajouter des informations sur la distance et le temps
                    distance_km = distance_m / 1000
                    time_min = estimated_time_s / 60 if estimated_time_s else None
                    
                    message_parts = message.split('\n')
                    # Insérer les informations de distance après le titre
                    new_message = message_parts[0] + '\n'
                    new_message += f"Distance: {distance_km:.2f} km\n"
                    if time_min:
                        new_message += f"Temps estime: {time_min:.1f} min\n"
                    new_message += '\n'.join(message_parts[1:])
                    message = new_message
                    
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
                                SET last_alert_at = to_timestamp(%s),
                                    last_alert_edge_u = %s,
                                    last_alert_edge_v = %s
                                WHERE driver_id = %s
                                """,
                                (now_ts, int(edge_u), int(edge_v), str(driver_id))
                            )
                            conn.commit()
                            alerts_sent += 1
                            print(f"  Alerte proactive envoyée au chauffeur {driver_id} ({phone_number})")
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
                        print(f"  Échec de l'envoi WhatsApp au chauffeur {driver_id}")
                        errors_count += 1
                
            except Exception as e:
                print(f"Erreur lors du traitement du chauffeur {driver_id}: {e}")
                errors_count += 1
                import traceback
                traceback.print_exc()
                continue
        
        result = {
            "alerts_envoyées": alerts_sent,
            "erreurs": errors_count,
            "statut": "succès" if errors_count == 0 else "succès_avec_erreurs"
        }
        print(f"Résumé: {alerts_sent} alertes anticipées envoyées, {errors_count} erreur(s)")
        return result
        
    except Exception as e:
        error_msg = f"Erreur critique lors de l'exécution des alertes: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {"alerts_envoyées": alerts_sent, "erreurs": errors_count, "statut": "erreur", "message": str(e)}

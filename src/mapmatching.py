"""
Module de map matching pour associer les points GPS aux routes du réseau routier.
Utilise OSMnx pour télécharger le réseau routier et GeoPandas pour le traitement spatial.
"""
import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.ops import nearest_points
import os

# Configuration OSMnx
ox.settings.use_cache = True
ox.settings.log_console = False
# Configurer le dossier de cache local
# Détecter si on est dans Docker ou local
if os.path.exists('/opt/airflow'):
    # Dans Docker (Airflow)
    cache_dir = '/opt/airflow/cache'
else:
    # En local
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
os.makedirs(cache_dir, exist_ok=True)
ox.settings.cache_folder = cache_dir

# Variables globales pour le cache du réseau routier
_cached_network = None
_cached_place = None

def charger_reseau_depuis_db():
    """
    Charge le réseau routier depuis PostgreSQL au lieu de le télécharger.
    Version optimisée qui utilise PostGIS pour des requêtes spatiales rapides.
    
    Returns:
    --------
    tuple (nodes_gdf, edges_gdf) or None
        GeoDataFrames des nœuds et arêtes, ou None si erreur
    """
    try:
        from src.Script_ETL import get_db_connection
        from shapely import wkt
        
        conn = get_db_connection()
        
        # Charger les nœuds
        nodes_query = """
            SELECT osmid, ST_AsText(geometry) as geometry_wkt, x, y
            FROM road_network_nodes
        """
        nodes_df = pd.read_sql(nodes_query, conn)
        
        if nodes_df.empty:
            print("⚠️ Aucun nœud trouvé dans road_network_nodes")
            print("   Exécuter scripts/load_road_network_to_db.py pour charger le réseau routier")
            conn.close()
            return None
        
        # Convertir la géométrie WKT en objets Shapely
        nodes_df['geometry'] = nodes_df['geometry_wkt'].apply(wkt.loads)
        nodes_gdf = gpd.GeoDataFrame(nodes_df.drop(columns=['geometry_wkt']), geometry='geometry', crs='EPSG:4326')
        nodes_gdf = nodes_gdf.set_index('osmid')
        
        # Charger les arêtes
        edges_query = """
            SELECT u, v, osmid, name, highway, ST_AsText(geometry) as geometry_wkt, length_m
            FROM road_network_edges
        """
        edges_df = pd.read_sql(edges_query, conn)
        
        if edges_df.empty:
            print("⚠️ Aucune arête trouvée dans road_network_edges")
            print("   Exécuter scripts/load_road_network_to_db.py pour charger le réseau routier")
            conn.close()
            return None
        
        # Convertir la géométrie WKT en objets Shapely
        edges_df['geometry'] = edges_df['geometry_wkt'].apply(wkt.loads)
        edges_gdf = gpd.GeoDataFrame(edges_df.drop(columns=['geometry_wkt']), geometry='geometry', crs='EPSG:4326')
        edges_gdf = edges_gdf.set_index(['u', 'v'])
        
        conn.close()
        
        print(f"✅ Réseau routier chargé depuis PostgreSQL: {len(nodes_gdf)} nœuds, {len(edges_gdf)} arêtes")
        return nodes_gdf, edges_gdf
        
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement depuis PostgreSQL: {e}")
        print("   Fallback vers téléchargement depuis OpenStreetMap...")
        import traceback
        traceback.print_exc()
        return None

def telecharger_reseau(place="Kinshasa, Democratic Republic of the Congo", network_type="drive", use_db=True):
    """
    Télécharge ou charge le réseau routier.
    
    Parameters:
    -----------
    place : str
        Nom du lieu (par défaut: Kinshasa)
    network_type : str
        Type de réseau ('drive', 'walk', 'bike', 'all')
    use_db : bool
        Si True, essaie de charger depuis PostgreSQL d'abord. Si False ou si erreur, télécharge depuis OSM.

    Returns:
    --------
    networkx.MultiDiGraph or True
        Graphe du réseau routier si téléchargé depuis OSM, True si chargé depuis DB
    """
    global _cached_network, _cached_place

    # Utiliser le cache si le même lieu est demandé
    if _cached_network is not None and _cached_place == place and 'edges' in _cached_network:
        if 'graph' in _cached_network:
            return _cached_network['graph']
        else:
            # Cache depuis DB (pas de graphe, juste edges)
            return True

    # Essayer d'abord de charger depuis PostgreSQL
    if use_db:
        result = charger_reseau_depuis_db()
        if result is not None:
            nodes_gdf, edges_gdf = result
            # Mettre en cache les GeoDataFrames (pas besoin du graphe NetworkX)
            _cached_network = {'nodes': nodes_gdf, 'edges': edges_gdf}
            _cached_place = place
            return True  # Indique que les données sont chargées depuis DB

    # Si échec ou use_db=False, télécharger depuis OSM (comportement original)
    try:
        if use_db:
            print("⚠️ Chargement depuis PostgreSQL échoué, téléchargement depuis OSM...")
        else:
            print("📥 Téléchargement du réseau routier depuis OpenStreetMap...")
        
        G = ox.graph_from_place(place, network_type=network_type)
        nodes, edges = ox.graph_to_gdfs(G)
        _cached_network = {'graph': G, 'nodes': nodes, 'edges': edges}
        _cached_place = place
        return G
    except Exception as e:
        print(f"❌ Erreur lors du téléchargement du réseau routier: {e}")
        return None

def associer_points_aux_routes(gdf_points, edges, max_distance=100):
    """
    Associe des points GPS aux routes les plus proches.
    Version optimisée utilisant sjoin_nearest pour la performance.

    Parameters:
    -----------
    gdf_points : geopandas.GeoDataFrame
        Points GPS à associer
    edges : geopandas.GeoDataFrame
        Arêtes du réseau routier
    max_distance : float
        Distance maximale (en mètres) pour associer un point à une route      

    Returns:
    --------
    geopandas.GeoDataFrame
        Points avec les informations de la route associée
    """
    if gdf_points.empty or edges.empty:
        return gdf_points

    try:
        # OPTIMISATION: Convertir max_distance de mètres en degrés approximatifs
        max_distance_deg = max_distance / 111000

        # OPTIMISATION: Simplifier l'extraction de u et v AVANT la jointure
        # Réinitialiser l'index pour avoir u et v comme colonnes
        edges_reset = edges.reset_index()
        
        # Vérifier que u et v existent (soit dans l'index MultiIndex, soit comme colonnes)
        if 'u' not in edges_reset.columns or 'v' not in edges_reset.columns:
            # Si u et v sont dans l'index MultiIndex
            if isinstance(edges.index, pd.MultiIndex):
                edges_reset['u'] = edges_reset.index.get_level_values(0)
                edges_reset['v'] = edges_reset.index.get_level_values(1)
            else:
                # Si pas d'index, créer des colonnes None
                edges_reset['u'] = None
                edges_reset['v'] = None

        # OPTIMISATION: Utiliser sjoin_nearest pour trouver la route la plus proche
        joined = gdf_points.sjoin_nearest(
            edges_reset,
            how='left',
            max_distance=max_distance_deg,
            distance_col='distance_to_road_deg'
        )
        
        # Convertir la distance en mètres
        if 'distance_to_road_deg' in joined.columns:
            joined['distance_to_road'] = joined['distance_to_road_deg'] * 111000
            joined = joined.drop(columns=['distance_to_road_deg'], errors='ignore')
        else:
            joined['distance_to_road'] = None

        # OPTIMISATION: Extraire edge_u et edge_v directement depuis les colonnes u et v
        if 'u' in joined.columns:
            joined['edge_u'] = joined['u']
        else:
            joined['edge_u'] = None
            
        if 'v' in joined.columns:
            joined['edge_v'] = joined['v']
        else:
            joined['edge_v'] = None
        
        # Nettoyer les colonnes en double et temporaires
        cols_to_drop = [col for col in joined.columns if col.endswith('_right') or col in ['u', 'v', 'index_right']]
        joined = joined.drop(columns=[c for c in cols_to_drop if c in joined.columns], errors='ignore')
        
        # S'assurer que les colonnes requises existent
        if 'osmid' not in joined.columns:
            joined['osmid'] = None
        if 'name' in joined.columns:
            joined['road_name'] = joined['name']
        elif 'road_name' not in joined.columns:
            joined['road_name'] = None
        
        # Filtrer les points qui n'ont pas de route associée (distance > max_distance)
        if 'distance_to_road' in joined.columns:
            mask_no_route = joined['distance_to_road'].isna() | (joined['distance_to_road'] > max_distance)
            joined.loc[mask_no_route, 'edge_u'] = None
            joined.loc[mask_no_route, 'edge_v'] = None
            joined.loc[mask_no_route, 'osmid'] = None
            joined.loc[mask_no_route, 'road_name'] = None
            joined.loc[mask_no_route, 'distance_to_road'] = None

        return joined.reset_index(drop=True)
        
    except Exception as e:
        print(f"Avertissement: sjoin_nearest a échoué ({e}). Fallback vers la méthode originale (plus lente).")
        # Fallback vers la méthode originale si sjoin_nearest échoue
        return _associer_points_aux_routes_fallback(gdf_points, edges, max_distance)

def _associer_points_aux_routes_fallback(gdf_points, edges, max_distance=100):
    """
    Méthode de fallback (plus lente) si sjoin_nearest échoue.
    """
    if gdf_points.empty or edges.empty:
        return gdf_points

    try:
        sindex = edges.sindex
    except AttributeError:
        sindex = None

    result_points = []
    
    # Limiter le nombre de points traités pour éviter les timeouts
    max_points = 200
    if len(gdf_points) > max_points:
        print(f"  Avertissement: Limitation à {max_points} points sur {len(gdf_points)} pour la performance")
        gdf_points = gdf_points.head(max_points)

    for idx, point_row in gdf_points.iterrows():
        point_geom = point_row.geometry

        if sindex is not None:
            possible_matches_index = list(sindex.intersection(point_geom.buffer(max_distance / 111000).bounds))
            possible_matches = edges.iloc[possible_matches_index]
        else:
            possible_matches = edges[edges.geometry.intersects(point_geom.buffer(max_distance / 111000))]

        if len(possible_matches) == 0:
            result_points.append({
                'geometry': point_geom,
                'osmid': None,
                'edge_u': None,
                'edge_v': None,
                'distance_to_road': None,
                'road_name': None,
                **{col: point_row[col] for col in gdf_points.columns if col != 'geometry'}
            })
            continue

        min_distance = float('inf')
        nearest_edge = None

        for edge_idx, edge_row in possible_matches.iterrows():
            try:
                nearest_pt = nearest_points(point_geom, edge_row.geometry)[1]
                distance = point_geom.distance(nearest_pt) * 111000

                if distance < min_distance:
                    min_distance = distance
                    nearest_edge = edge_row.copy()
                    if isinstance(edge_idx, tuple) and len(edge_idx) >= 2:
                        nearest_edge['u'] = edge_idx[0]
                        nearest_edge['v'] = edge_idx[1]
            except Exception:
                continue

        if nearest_edge is not None and min_distance <= max_distance:
            edge_u = nearest_edge.get('u', None)
            edge_v = nearest_edge.get('v', None)

            result_points.append({
                'geometry': point_geom,
                'osmid': nearest_edge.get('osmid', None),
                'edge_u': edge_u,
                'edge_v': edge_v,
                'distance_to_road': min_distance,
                'road_name': nearest_edge.get('name', 'Unknown'),
                **{col: point_row[col] for col in gdf_points.columns if col != 'geometry'}
            })
        else:
            result_points.append({
                'geometry': point_geom,
                'osmid': None,
                'edge_u': None,
                'edge_v': None,
                'distance_to_road': None,
                'road_name': None,
                **{col: point_row[col] for col in gdf_points.columns if col != 'geometry'}
            })

    result_gdf = gpd.GeoDataFrame(result_points, crs=gdf_points.crs)
    return result_gdf

def effectuer_mapmatching(df, place="Kinshasa, Democratic Republic of the Congo", max_distance=50, max_points=50):
    """
    Fonction principale pour effectuer le map matching sur un DataFrame de points GPS.
    OPTIMISÉE: Limite drastiquement le nombre de points traités pour éviter les timeouts.
    
    IMPORTANT - FLUX DE DONNÉES:
    ----------------------------
    Les données GPS dans 'df' proviennent de la table gps_points (collectées par l'app mobile).
    Cette fonction:
    1. Reçoit les points GPS collectés (latitude, longitude, driver_id, speed, timestamp)
    2. Télécharge le réseau routier depuis OpenStreetMap (OSM) via OSMnx
    3. Associe chaque point GPS au tronçon de route OSM le plus proche
    4. Retourne les points GPS enrichis avec les informations de route (edge_u, edge_v, road_name, etc.)
    
    Le map matching consiste donc à:
    - Points GPS collectés (gps_points) ← Source: App mobile
    - Réseau routier (OSM) ← Source: OpenStreetMap (téléchargé en ligne)
    - Association spatiale ← Trouver la route la plus proche de chaque point GPS

    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame avec les colonnes latitude, longitude, et autres colonnes
    place : str
        Nom du lieu pour télécharger le réseau routier depuis OpenStreetMap (par défaut: Kinshasa)
    max_distance : float
        Distance maximale (en mètres) pour associer un point à une route (par défaut: 50m au lieu de 100m)
    max_points : int
        Nombre maximum de points GPS à traiter (par défaut: 50 au lieu de 100)
        Limite le temps d'exécution pour éviter les timeouts dans Airflow

    Returns:
    --------
    pandas.DataFrame
        DataFrame enrichi avec les informations des routes
    """
    # Gérer le cas où le DataFrame est vide
    if df.empty:
        return df

    # Vérifier que les colonnes nécessaires existent
    if 'latitude' not in df.columns or 'longitude' not in df.columns:
        print("Erreur: Le DataFrame doit contenir les colonnes 'latitude' et 'longitude'")
        return df

    try:
        # OPTIMISATION: Si très peu de points, ne pas faire de mapmatching
        if len(df) < 5:
            print(f"Trop peu de points ({len(df)}), mapmatching ignoré")
            df_result = df.copy()
            df_result['edge_u'] = None
            df_result['edge_v'] = None
            df_result['osmid'] = None
            df_result['road_name'] = None
            df_result['distance_to_road'] = None
            return df_result

        # OPTIMISATION: Limiter drastiquement le nombre de points traités
        original_len = len(df)
        if original_len > max_points:
            print(f"Limitation à {max_points} points sur {original_len} pour optimiser les performances")
            # OPTIMISATION: Prendre un échantillon représentatif (les plus récents + échantillonnage)
            # Prendre les 30% les plus récents + échantillonner le reste
            recent_count = min(max_points // 3, original_len)
            sample_count = max_points - recent_count
            
            df_recent = df.tail(recent_count).copy()
            df_rest = df.head(original_len - recent_count)
            
            if len(df_rest) > 0 and sample_count > 0:
                step = max(1, len(df_rest) // sample_count)
                df_sample = df_rest.iloc[::step].head(sample_count).copy()
                df = pd.concat([df_recent, df_sample]).reset_index(drop=True)
            else:
                df = df_recent
        
        # OPTIMISATION: Charger le réseau routier depuis PostgreSQL (plus rapide) ou OSM
        print("🌐 Chargement du réseau routier...")
        result = telecharger_reseau(place, use_db=True)

        if result is None:
            print("❌ Avertissement: Impossible de charger le réseau routier (ni PostgreSQL ni OSM).")
            print("   Retour des données sans map matching.")
            df_result = df.copy()
            df_result['edge_u'] = None
            df_result['edge_v'] = None
            df_result['osmid'] = None
            df_result['road_name'] = None
            df_result['distance_to_road'] = None
            return df_result

        # OPTIMISATION: Récupérer les arêtes du réseau depuis le cache
        global _cached_network
        if _cached_network is None or 'edges' not in _cached_network:
            if result is True:
                # Chargé depuis DB mais cache vide (ne devrait pas arriver)
                print("❌ Erreur: réseau routier DB chargé mais cache vide")
                df_result = df.copy()
                df_result['edge_u'] = None
                df_result['edge_v'] = None
                df_result['osmid'] = None
                df_result['road_name'] = None
                df_result['distance_to_road'] = None
                return df_result
            else:
                # Téléchargé depuis OSM, convertir en GeoDataFrame
                print("Conversion du réseau OSM en GeoDataFrame...")
                G = result
                nodes, edges = ox.graph_to_gdfs(G)
                _cached_network = {'graph': G, 'nodes': nodes, 'edges': edges}
        else:
            edges = _cached_network['edges']
            if result is True:
                print(f"✅ Utilisation du réseau routier depuis PostgreSQL ({len(edges)} arêtes)")
            else:
                print(f"✅ Utilisation du cache du réseau routier ({len(edges)} arêtes)")

        # OPTIMISATION: S'assurer que les edges ont u et v accessibles
        # Si les edges viennent de DB, elles ont déjà u et v dans l'index MultiIndex
        if isinstance(edges.index, pd.MultiIndex):
            # OK, u et v sont dans l'index
            pass
        elif 'u' not in edges.columns or 'v' not in edges.columns:
            # Si ce n'est pas un MultiIndex et pas de colonnes u/v, essayer de les extraire
            if result is not True and result is not None:
                # Réessayer depuis le graph OSM
                G = result
                nodes, edges = ox.graph_to_gdfs(G)
                _cached_network['edges'] = edges

        # Créer un GeoDataFrame à partir des points GPS
        geometry = [Point(lon, lat) for lon, lat in zip(df['longitude'], df['latitude'])]
        gdf_points = gpd.GeoDataFrame(df, geometry=geometry, crs='EPSG:4326')

        # S'assurer que les edges ont le même CRS
        if edges.crs is None:
            edges.set_crs('EPSG:4326', inplace=True)
        elif edges.crs != gdf_points.crs:
            edges = edges.to_crs(gdf_points.crs)

        # OPTIMISATION: Associer les points aux routes (avec max_distance réduit pour la performance)
        print(f"Association de {len(gdf_points)} points aux routes (max_distance={max_distance}m)...")
        gdf_matched = associer_points_aux_routes(gdf_points, edges, max_distance=max_distance)

        # Convertir en DataFrame pandas (supprimer la colonne geometry)
        result_df = pd.DataFrame(gdf_matched.drop(columns='geometry', errors='ignore'))
        
        # Compter les points associés
        matched_count = result_df['edge_u'].notna().sum()
        print(f"Map matching terminé: {matched_count}/{len(result_df)} points associés aux routes ({matched_count/len(result_df)*100:.1f}%)")
        
        return result_df
        
    except Exception as e:
        print(f"Erreur lors du map matching: {e}")
        import traceback
        traceback.print_exc()
        # En cas d'erreur, retourner les données sans map matching plutôt que de planter
        df_result = df.copy()
        df_result['edge_u'] = None
        df_result['edge_v'] = None
        df_result['osmid'] = None
        df_result['road_name'] = None
        df_result['distance_to_road'] = None
        return df_result

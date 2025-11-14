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

def telecharger_reseau(place="Kinshasa, Democratic Republic of the Congo", network_type="drive"):
    """
    Télécharge le réseau routier pour un lieu donné.

    Parameters:
    -----------
    place : str
        Nom du lieu (par défaut: Kinshasa)
    network_type : str
        Type de réseau ('drive', 'walk', 'bike', 'all')

    Returns:
    --------
    networkx.MultiDiGraph
        Graphe du réseau routier
    """
    global _cached_network, _cached_place

    # Utiliser le cache si le même lieu est demandé
    if _cached_network is not None and _cached_place == place:
        return _cached_network['graph']

    try:
        # Télécharger le réseau routier
        G = ox.graph_from_place(place, network_type=network_type)

        # Convertir en GeoDataFrame pour faciliter le traitement
        nodes, edges = ox.graph_to_gdfs(G)

        # Mettre en cache
        _cached_network = {'graph': G, 'nodes': nodes, 'edges': edges}
        _cached_place = place

        return G
    except Exception as e:
        print(f"Erreur lors du téléchargement du réseau routier: {e}")
        # Retourner None en cas d'erreur (connexion internet, etc.)
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

    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame avec les colonnes latitude, longitude, et autres colonnes
    place : str
        Nom du lieu pour télécharger le réseau routier
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
        
        # OPTIMISATION: Télécharger le réseau routier (utilise le cache si disponible)
        print("Chargement du réseau routier (cache si disponible)...")
        G = telecharger_reseau(place)

        if G is None:
            print("Avertissement: Impossible de télécharger le réseau routier. Retour des données sans map matching.")
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
            print("Conversion du réseau en GeoDataFrame...")
            nodes, edges = ox.graph_to_gdfs(G)
            _cached_network = {'graph': G, 'nodes': nodes, 'edges': edges}
        else:
            edges = _cached_network['edges']
            print(f"Utilisation du cache du réseau routier ({len(edges)} arêtes)")

        # OPTIMISATION: S'assurer que les edges ont u et v accessibles
        if not isinstance(edges.index, pd.MultiIndex):
            # Si ce n'est pas un MultiIndex, essayer de le réinitialiser
            if 'u' not in edges.columns or 'v' not in edges.columns:
                # Réessayer depuis le graph
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

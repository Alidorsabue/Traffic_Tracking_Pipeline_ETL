#!/usr/bin/env python3
"""
Script pour télécharger le réseau routier depuis OpenStreetMap
et le stocker dans PostgreSQL avec PostGIS.
À exécuter UNE SEULE FOIS pour initialiser le réseau routier.
"""

import sys
import os
import gc  # Pour libérer la mémoire
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely import wkt
from src.Script_ETL import get_db_connection
from datetime import datetime
import traceback

def download_and_load_road_network(place="Kinshasa, Democratic Republic of the Congo", network_type="drive", place_label=None, filter_main_roads=True):
    """
    Télécharge le réseau routier depuis OSM et le charge dans PostgreSQL.
    OPTIMISÉ: Filtre les routes principales et télécharge par zones si nécessaire.
    
    Parameters:
    -----------
    place : str
        Nom du lieu pour télécharger le réseau routier (ex: "Kinshasa, Democratic Republic of the Congo")
    network_type : str
        Type de réseau ('drive', 'walk', 'bike', 'all')
    place_label : str, optional
        Label court pour identifier la ville dans la base de données (ex: "Kinshasa", "Lubumbashi")
        Si None, extrait automatiquement depuis 'place'
    filter_main_roads : bool
        Si True, télécharge uniquement les routes principales (motorway, trunk, primary, secondary)
        Pour réduire l'utilisation mémoire. Par défaut: True
    """
    # Extraire le label de la ville si non fourni
    if place_label is None:
        # Extraire le premier mot (nom de la ville) depuis "Ville, Pays"
        place_label = place.split(',')[0].strip()
    
    print("=" * 80)
    print("TÉLÉCHARGEMENT ET CHARGEMENT DU RÉSEAU ROUTIER")
    print("=" * 80)
    print(f"Lieu: {place}")
    print(f"Label ville: {place_label}")
    print(f"Type de réseau: {network_type}")
    print(f"Filtre routes principales: {filter_main_roads}")
    print(f"Date: {datetime.now()}\n")
    
    conn = None
    cursor = None
    
    try:
        # OPTIMISATION: Utiliser custom_filter pour télécharger uniquement les routes principales
        # Cela réduit drastiquement la taille du téléchargement
        custom_filter = None
        if filter_main_roads:
            # Filtrer seulement les routes principales (autoroutes, routes principales, secondaires)
            # Exclure les routes locales (residential, service, etc.) qui sont trop nombreuses
            custom_filter = '["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]'
            print("[ETAPE 1/4] Téléchargement du réseau routier depuis OpenStreetMap...")
            print("   ⚠️ OPTIMISATION: Téléchargement UNIQUEMENT des routes principales")
            print("   (motorway, trunk, primary, secondary, tertiary)")
            print("   Cela réduit la taille du téléchargement et l'utilisation mémoire.")
            print("   Cela peut prendre plusieurs minutes...")
        else:
            print("[ETAPE 1/4] Téléchargement du réseau routier depuis OpenStreetMap...")
            print("   ⚠️ ATTENTION: Téléchargement de TOUTES les routes (peut être très lourd)")
            print("   Cela peut prendre 30-60 minutes et utiliser beaucoup de mémoire...")
        
        # Télécharger avec le filtre si spécifié
        if custom_filter:
            G = ox.graph_from_place(place, network_type=network_type, custom_filter=custom_filter)
        else:
            G = ox.graph_from_place(place, network_type=network_type)
        
        print(f"[SUCCESS] Réseau routier téléchargé: {len(G.nodes())} nœuds, {len(G.edges())} arêtes")
        
        if filter_main_roads:
            print(f"   Note: Seulement les routes principales ont été téléchargées")
            print(f"   Cela représente ~5-10% du réseau complet mais couvre 90%+ du trafic")
        
        # Convertir en GeoDataFrames
        print("\n[ETAPE 2/4] Conversion en GeoDataFrames...")
        print("   Cela peut prendre quelques minutes pour de grandes villes...")
        
        # OPTIMISATION: Libérer la mémoire dès que possible
        # Convertir d'abord les nodes, puis les edges séparément
        nodes = None
        edges = None
        
        try:
            nodes, edges = ox.graph_to_gdfs(G)
            print(f"[SUCCESS] Conversion terminée")
            print(f"   Nœuds: {len(nodes)}")
            print(f"   Arêtes: {len(edges)}")
            
            # Libérer le graph de la mémoire
            del G
            import gc
            gc.collect()
        except MemoryError as e:
            print(f"[ERROR] Erreur de mémoire lors de la conversion: {e}")
            print("   SOLUTION: Utiliser filter_main_roads=True pour télécharger seulement les routes principales")
            print("   Ou diviser la ville en zones plus petites")
            raise
        
        # Se connecter à la base de données
        print("\n[ETAPE 3/4] Connexion à la base de données PostgreSQL...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Vérifier si PostGIS est installé et activé
        try:
            # Vérifier si l'extension existe
            cursor.execute("""
                SELECT extname, extversion 
                FROM pg_extension 
                WHERE extname = 'postgis';
            """)
            postgis_ext = cursor.fetchone()
            
            if postgis_ext:
                print(f"[SUCCESS] PostGIS installé: version {postgis_ext[1]}")
                # Vérifier la version PostGIS
                cursor.execute("SELECT PostGIS_version();")
                postgis_version = cursor.fetchone()
                if postgis_version:
                    print(f"   Version PostGIS: {postgis_version[0]}")
            else:
                print("[WARNING] PostGIS n'est pas activé sur cette base de données")
                print("   ACTION REQUISE: Exécuter en tant qu'administrateur:")
                print("   CREATE EXTENSION IF NOT EXISTS postgis;")
                print("\n   Si vous avez une erreur 'permission denied':")
                print("   1. Connectez-vous avec un compte administrateur (ex: postgres)")
                print("   2. Ou demandez à l'administrateur de la base de données d'activer PostGIS")
                
                # Vérifier si PostGIS est disponible mais pas activé
                cursor.execute("SELECT * FROM pg_available_extensions WHERE name = 'postgis';")
                available = cursor.fetchone()
                if available:
                    print(f"   [SUCCESS] PostGIS est disponible sur le serveur mais pas activé")
                    print(f"      Version disponible: {available[2]}")
                else:
                    print("   [ERROR] PostGIS n'est pas installé sur le serveur PostgreSQL")
                    print("      Contactez l'administrateur pour installer PostGIS")
                
                cursor.close()
                conn.close()
                return False
        except Exception as e:
            print(f"[WARNING] Erreur lors de la vérification PostGIS: {e}")
            print("   PostGIS pourrait ne pas être installé ou activé")
            print("   Exécuter manuellement en tant qu'administrateur: CREATE EXTENSION IF NOT EXISTS postgis;")
            cursor.close()
            conn.close()
            return False
        
        # Supprimer uniquement les données pour cette ville (pas toutes les villes)
        print(f"\n[INFO] Nettoyage des anciennes données pour {place_label}...")
        try:
            delete_nodes_query = "DELETE FROM road_network_nodes WHERE place = %s;"
            delete_edges_query = "DELETE FROM road_network_edges WHERE place = %s;"
            
            cursor.execute(delete_nodes_query, (place_label,))
            deleted_nodes = cursor.rowcount
            cursor.execute(delete_edges_query, (place_label,))
            deleted_edges = cursor.rowcount
            conn.commit()
            print(f"[SUCCESS] {deleted_nodes} nœuds et {deleted_edges} arêtes supprimés pour {place_label}")
        except Exception as e:
            print(f"[WARNING] Erreur lors du nettoyage (peut-être que les tables sont vides): {e}")
            conn.rollback()
        
        # Charger les nœuds par petits lots pour optimiser la mémoire
        print(f"\n[ETAPE 4/5] Chargement de {len(nodes)} nœuds dans PostgreSQL...")
        print("   Traitement par lots de 5000 pour optimiser la mémoire...")
        
        total_nodes_inserted = 0
        batch_size = 5000
        total_nodes = len(nodes)
        
        for batch_start in range(0, total_nodes, batch_size):
            batch_end = min(batch_start + batch_size, total_nodes)
            nodes_batch = nodes.iloc[batch_start:batch_end]
            
            nodes_to_insert = []
            skipped_nodes = 0
            
            for idx, node in nodes_batch.iterrows():
                try:
                    geom = node.geometry
                    if geom is not None:
                        # Extraire l'osmid (peut être un MultiIndex)
                        if isinstance(idx, (list, tuple)):
                            osmid = int(idx[0]) if len(idx) > 0 else int(idx)
                        else:
                            osmid = int(idx)
                        
                        nodes_to_insert.append((
                            place_label,
                            osmid,
                            geom.wkt,  # geometry as WKT
                            float(geom.x),
                            float(geom.y)
                        ))
                    else:
                        skipped_nodes += 1
                except Exception as e:
                    skipped_nodes += 1
                    continue
            
            # Insérer ce lot
            if nodes_to_insert:
                insert_nodes_query = """
                    INSERT INTO road_network_nodes (place, osmid, geometry, x, y)
                    VALUES (%s, %s, ST_GeomFromText(%s, 4326), %s, %s)
                    ON CONFLICT (place, osmid) DO NOTHING
                """
                from psycopg2.extras import execute_batch
                execute_batch(cursor, insert_nodes_query, nodes_to_insert, page_size=1000)
                conn.commit()
                total_nodes_inserted += len(nodes_to_insert)
            
            print(f"   Lot {batch_start//batch_size + 1}: {len(nodes_to_insert)} nœuds insérés ({batch_end}/{total_nodes})")
            
            # Libérer la mémoire
            del nodes_to_insert
            import gc
            gc.collect()
        
        print(f"[SUCCESS] {total_nodes_inserted} nœuds chargés dans PostgreSQL pour {place_label}")
        
        # Libérer nodes de la mémoire
        del nodes
        import gc
        gc.collect()
        
        # Charger les arêtes par petits lots pour optimiser la mémoire
        print(f"\n[ETAPE 5/5] Chargement de {len(edges)} arêtes dans PostgreSQL...")
        print("   Traitement par lots de 5000 pour optimiser la mémoire...")
        
        total_edges_inserted = 0
        skipped_edges_total = 0
        batch_size = 5000
        total_edges = len(edges)
        
        for batch_start in range(0, total_edges, batch_size):
            batch_end = min(batch_start + batch_size, total_edges)
            edges_batch = edges.iloc[batch_start:batch_end]
            
            edges_to_insert = []
            skipped_edges = 0
            
            for idx, edge in edges_batch.iterrows():
                try:
                    geom = edge.geometry
                    if geom is None:
                        skipped_edges += 1
                        continue
                    
                    # Extraire u et v depuis l'index MultiIndex
                    if isinstance(idx, tuple) and len(idx) >= 2:
                        u = int(idx[0])
                        v = int(idx[1])
                    else:
                        skipped_edges += 1
                        continue
                    
                    osmid = None
                    if 'osmid' in edge and pd.notna(edge.get('osmid')):
                        osmid_val = edge.get('osmid')
                        if isinstance(osmid_val, (list, tuple)) and len(osmid_val) > 0:
                            osmid = int(osmid_val[0])
                        else:
                            try:
                                osmid = int(osmid_val)
                            except (ValueError, TypeError):
                                osmid = None
                    
                    name = None
                    if 'name' in edge and pd.notna(edge.get('name')):
                        name_str = str(edge.get('name'))
                        if len(name_str) <= 255:
                            name = name_str
                    
                    highway = None
                    if 'highway' in edge and pd.notna(edge.get('highway')):
                        highway_str = str(edge.get('highway'))
                        if len(highway_str) <= 50:
                            highway = highway_str
                    
                    length = None
                    if 'length' in edge and pd.notna(edge.get('length')):
                        try:
                            length = float(edge.get('length'))
                        except (ValueError, TypeError):
                            length = None
                    
                    edges_to_insert.append((
                        place_label, u, v, osmid, name, highway, geom.wkt, length
                    ))
                except Exception as e:
                    skipped_edges += 1
                    continue
            
            skipped_edges_total += skipped_edges
            
            # Insérer ce lot
            if edges_to_insert:
                insert_edges_query = """
                    INSERT INTO road_network_edges (place, u, v, osmid, name, highway, geometry, length_m)
                    VALUES (%s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                    ON CONFLICT (place, u, v, osmid) DO NOTHING
                """
                from psycopg2.extras import execute_batch
                execute_batch(cursor, insert_edges_query, edges_to_insert, page_size=1000)
                conn.commit()
                total_edges_inserted += len(edges_to_insert)
            
            print(f"   Lot {batch_start//batch_size + 1}: {len(edges_to_insert)} arêtes insérées ({batch_end}/{total_edges})")
            
            # Libérer la mémoire
            del edges_to_insert
            import gc
            gc.collect()
        
        if skipped_edges_total > 0:
            print(f"   {skipped_edges_total} arêtes ignorées au total (géométrie invalide ou erreur)")
        
        print(f"[SUCCESS] {total_edges_inserted} arêtes chargées dans PostgreSQL pour {place_label}")
        
        # Libérer edges de la mémoire
        del edges
        import gc
        gc.collect()
        
        # Statistiques finales (pour cette ville)
        cursor.execute("SELECT COUNT(*) FROM road_network_nodes WHERE place = %s;", (place_label,))
        node_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM road_network_edges WHERE place = %s;", (place_label,))
        edge_count = cursor.fetchone()[0]
        
        # Statistiques globales (toutes les villes)
        cursor.execute("SELECT COUNT(*) FROM road_network_nodes;")
        total_nodes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM road_network_edges;")
        total_edges = cursor.fetchone()[0]
        
        # Liste des villes chargées
        cursor.execute("SELECT DISTINCT place, COUNT(*) as count FROM road_network_nodes GROUP BY place;")
        places_loaded = cursor.fetchall()
        
        print("\n" + "=" * 80)
        print(f"[SUCCESS] RÉSEAU ROUTIER CHARGÉ AVEC SUCCÈS POUR {place_label.upper()}")
        print("=" * 80)
        print(f"   {place_label}: {node_count} nœuds, {edge_count} arêtes")
        print(f"   Total (toutes villes): {total_nodes} nœuds, {total_edges} arêtes")
        if places_loaded:
            print(f"   Villes chargées: {', '.join([f'{p[0]} ({p[1]} nœuds)' for p in places_loaded])}")
        print(f"   Date de chargement: {datetime.now()}")
        print("=" * 80)
        print("\n[INFO] Le mapmatching utilisera maintenant ces données depuis PostgreSQL")
        print("   au lieu de télécharger depuis OpenStreetMap à chaque fois.\n")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n[ERROR] ERREUR lors du chargement du réseau routier: {e}")
        traceback.print_exc()
        if conn:
            conn.rollback()
            if cursor:
                cursor.close()
            conn.close()
        return False

if __name__ == "__main__":
    print("ATTENTION: Ce script télécharge le réseau routier depuis OpenStreetMap")
    print("   et le stocke dans PostgreSQL. Cela peut prendre 10-30 minutes par ville.\n")
    
    # Liste des villes à charger
    # OPTIMISATION: filter_main_roads=True pour réduire l'utilisation mémoire
    # Cela télécharge seulement les routes principales (motorway, trunk, primary, secondary, tertiary)
    # Ces routes couvrent 90%+ du trafic mais représentent seulement 5-10% du réseau total
    places_to_load = [
        {
            "place": "Kinshasa, Democratic Republic of the Congo",
            "label": "Kinshasa",
            "network_type": "drive",
            "filter_main_roads": True  # OPTIMISATION: Seulement les routes principales
        },
        {
            "place": "Lubumbashi, Democratic Republic of the Congo",
            "label": "Lubumbashi",
            "network_type": "drive",
            "filter_main_roads": True  # OPTIMISATION: Seulement les routes principales
        }
    ]
    
    print(f"Villes à charger: {len(places_to_load)}")
    for i, city in enumerate(places_to_load, 1):
        print(f"   {i}. {city['label']}")
    print()
    
    all_success = True
    results = []
    
    for city_info in places_to_load:
        print(f"\n{'='*80}")
        print(f"[INFO] CHARGEMENT DE {city_info['label'].upper()}")
        print(f"{'='*80}\n")
        
        success = download_and_load_road_network(
            place=city_info["place"],
            place_label=city_info["label"],
            network_type=city_info["network_type"],
            filter_main_roads=city_info.get("filter_main_roads", True)  # Par défaut True pour optimiser
        )
        
        results.append({
            "city": city_info["label"],
            "success": success
        })
        
        if not success:
            all_success = False
            print(f"\n[WARNING] Échec du chargement pour {city_info['label']}")
            response = input(f"\nContinuer avec la ville suivante? (o/n): ").strip().lower()
            if response != 'o':
                break
    
    # Résumé final
    print("\n" + "=" * 80)
    print("[INFO] RÉSUMÉ DU CHARGEMENT")
    print("=" * 80)
    for result in results:
        status = "[SUCCESS] Succès" if result["success"] else "[ERROR] Échec"
        print(f"   {result['city']}: {status}")
    print("=" * 80)
    
    if all_success:
        print("\n[SUCCESS] Tous les réseaux routiers sont maintenant stockés dans PostgreSQL.")
        print("   Le mapmatching utilisera automatiquement ces données.")
        print("\n[INFO] Prochaine étape: Modifier src/mapmatching.py pour utiliser ces données.")
    else:
        print("\n[WARNING] Certains réseaux routiers n'ont pas pu être chargés.")
        print("   Vérifier les logs ci-dessus pour plus de détails.")

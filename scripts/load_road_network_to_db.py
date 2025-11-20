#!/usr/bin/env python3
"""
Script pour télécharger le réseau routier depuis OpenStreetMap
et le stocker dans PostgreSQL avec PostGIS.
À exécuter UNE SEULE FOIS pour initialiser le réseau routier.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely import wkt
from src.Script_ETL import get_db_connection
from datetime import datetime
import traceback

def download_and_load_road_network(place="Kinshasa, Democratic Republic of the Congo", network_type="drive"):
    """
    Télécharge le réseau routier depuis OSM et le charge dans PostgreSQL.
    
    Parameters:
    -----------
    place : str
        Nom du lieu pour télécharger le réseau routier
    network_type : str
        Type de réseau ('drive', 'walk', 'bike', 'all')
    """
    print("=" * 80)
    print("TÉLÉCHARGEMENT ET CHARGEMENT DU RÉSEAU ROUTIER")
    print("=" * 80)
    print(f"Lieu: {place}")
    print(f"Type de réseau: {network_type}")
    print(f"Date: {datetime.now()}\n")
    
    conn = None
    cursor = None
    
    try:
        # Télécharger le réseau routier depuis OSM
        print("🔄 [ÉTAPE 1/4] Téléchargement du réseau routier depuis OpenStreetMap...")
        print("   Cela peut prendre plusieurs minutes...")
        
        G = ox.graph_from_place(place, network_type=network_type)
        print(f"✅ Réseau routier téléchargé: {len(G.nodes())} nœuds, {len(G.edges())} arêtes")
        
        # Convertir en GeoDataFrames
        print("\n📊 [ÉTAPE 2/4] Conversion en GeoDataFrames...")
        nodes, edges = ox.graph_to_gdfs(G)
        print(f"✅ Conversion terminée")
        print(f"   Nœuds: {len(nodes)}")
        print(f"   Arêtes: {len(edges)}")
        
        # Se connecter à la base de données
        print("\n💾 [ÉTAPE 3/4] Connexion à la base de données PostgreSQL...")
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
                print(f"✅ PostGIS installé: version {postgis_ext[1]}")
                # Vérifier la version PostGIS
                cursor.execute("SELECT PostGIS_version();")
                postgis_version = cursor.fetchone()
                if postgis_version:
                    print(f"   Version PostGIS: {postgis_version[0]}")
            else:
                print("⚠️  PostGIS n'est pas activé sur cette base de données")
                print("   ACTION REQUISE: Exécuter en tant qu'administrateur:")
                print("   CREATE EXTENSION IF NOT EXISTS postgis;")
                print("\n   Si vous avez une erreur 'permission denied':")
                print("   1. Connectez-vous avec un compte administrateur (ex: postgres)")
                print("   2. Ou demandez à l'administrateur de la base de données d'activer PostGIS")
                
                # Vérifier si PostGIS est disponible mais pas activé
                cursor.execute("SELECT * FROM pg_available_extensions WHERE name = 'postgis';")
                available = cursor.fetchone()
                if available:
                    print(f"   ✅ PostGIS est disponible sur le serveur mais pas activé")
                    print(f"      Version disponible: {available[2]}")
                else:
                    print("   ❌ PostGIS n'est pas installé sur le serveur PostgreSQL")
                    print("      Contactez l'administrateur pour installer PostGIS")
                
                cursor.close()
                conn.close()
                return False
        except Exception as e:
            print(f"⚠️  Erreur lors de la vérification PostGIS: {e}")
            print("   PostGIS pourrait ne pas être installé ou activé")
            print("   Exécuter manuellement en tant qu'administrateur: CREATE EXTENSION IF NOT EXISTS postgis;")
            cursor.close()
            conn.close()
            return False
        
        # Vider les tables existantes
        print("\n🗑️  Nettoyage des anciennes données...")
        try:
            cursor.execute("TRUNCATE TABLE road_network_nodes CASCADE;")
            cursor.execute("TRUNCATE TABLE road_network_edges CASCADE;")
            conn.commit()
            print("✅ Anciennes données supprimées")
        except Exception as e:
            print(f"⚠️  Erreur lors du nettoyage (peut-être que les tables sont vides): {e}")
            conn.rollback()
        
        # Charger les nœuds
        print(f"\n📥 [ÉTAPE 4/4] Chargement de {len(nodes)} nœuds dans PostgreSQL...")
        nodes_to_insert = []
        skipped_nodes = 0
        
        for idx, node in nodes.iterrows():
            try:
                geom = node.geometry
                if geom is not None:
                    # Extraire l'osmid (peut être un MultiIndex)
                    if isinstance(idx, (list, tuple)):
                        osmid = int(idx[0]) if len(idx) > 0 else int(idx)
                    else:
                        osmid = int(idx)
                    
                    nodes_to_insert.append((
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
        
        if skipped_nodes > 0:
            print(f"   {skipped_nodes} nœuds ignorés (géométrie invalide)")
        
        # Insérer les nœuds par batch
        if nodes_to_insert:
            insert_nodes_query = """
                INSERT INTO road_network_nodes (osmid, geometry, x, y)
                VALUES (%s, ST_GeomFromText(%s, 4326), %s, %s)
                ON CONFLICT (osmid) DO NOTHING
            """
            from psycopg2.extras import execute_batch
            execute_batch(cursor, insert_nodes_query, nodes_to_insert, page_size=1000)
            conn.commit()
            print(f"✅ {len(nodes_to_insert)} nœuds chargés dans PostgreSQL")
        else:
            print("⚠️  Aucun nœud à insérer")
        
        # Charger les arêtes
        print(f"\n📥 Chargement de {len(edges)} arêtes dans PostgreSQL...")
        edges_to_insert = []
        skipped_edges = 0
        
        for idx, edge in edges.iterrows():
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
                    u, v, osmid, name, highway, geom.wkt, length
                ))
            except Exception as e:
                skipped_edges += 1
                continue
        
        if skipped_edges > 0:
            print(f"   {skipped_edges} arêtes ignorées (géométrie invalide ou erreur)")
        
        # Insérer les arêtes par batch
        if edges_to_insert:
            insert_edges_query = """
                INSERT INTO road_network_edges (u, v, osmid, name, highway, geometry, length_m)
                VALUES (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                ON CONFLICT (u, v, osmid) DO NOTHING
            """
            from psycopg2.extras import execute_batch
            execute_batch(cursor, insert_edges_query, edges_to_insert, page_size=1000)
            conn.commit()
            print(f"✅ {len(edges_to_insert)} arêtes chargées dans PostgreSQL")
        else:
            print("⚠️  Aucune arête à insérer")
        
        # Statistiques finales
        cursor.execute("SELECT COUNT(*) FROM road_network_nodes;")
        node_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM road_network_edges;")
        edge_count = cursor.fetchone()[0]
        
        print("\n" + "=" * 80)
        print("✅ RÉSEAU ROUTIER CHARGÉ AVEC SUCCÈS")
        print("=" * 80)
        print(f"   Nœuds dans PostgreSQL: {node_count}")
        print(f"   Arêtes dans PostgreSQL: {edge_count}")
        print(f"   Date de chargement: {datetime.now()}")
        print("=" * 80)
        print("\n💡 Le mapmatching utilisera maintenant ces données depuis PostgreSQL")
        print("   au lieu de télécharger depuis OpenStreetMap à chaque fois.\n")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n❌ ERREUR lors du chargement du réseau routier: {e}")
        traceback.print_exc()
        if conn:
            conn.rollback()
            if cursor:
                cursor.close()
            conn.close()
        return False

if __name__ == "__main__":
    print("⚠️  ATTENTION: Ce script télécharge le réseau routier depuis OpenStreetMap")
    print("   et le stocke dans PostgreSQL. Cela peut prendre 10-30 minutes.\n")
    
    success = download_and_load_road_network(
        place="Kinshasa, Democratic Republic of the Congo",
        network_type="drive"
    )
    
    if success:
        print("\n✅ Le réseau routier est maintenant stocké dans PostgreSQL.")
        print("   Le mapmatching utilisera automatiquement ces données.")
        print("\n📝 Prochaine étape: Modifier src/mapmatching.py pour utiliser ces données.")
    else:
        print("\n❌ Échec du chargement du réseau routier.")
        print("   Vérifier les logs ci-dessus pour plus de détails.")

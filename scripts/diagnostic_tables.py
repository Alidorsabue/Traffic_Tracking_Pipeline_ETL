#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de diagnostic pour vérifier pourquoi les tables sont vides.
Vérifie chaque étape de la chaîne de traitement des données.
"""

import sys
import os
import locale

# Forcer l'encodage UTF-8 pour éviter les problèmes d'encodage
if sys.platform == 'win32':
    # Sur Windows, essayer de définir l'encodage UTF-8
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# S'assurer que le chemin est encodé correctement
script_dir = os.path.dirname(os.path.abspath(__file__))
if isinstance(script_dir, bytes):
    script_dir = script_dir.decode('utf-8')

sys.path.insert(0, os.path.join(script_dir, '..'))

from src.Script_ETL import get_db_connection
import pandas as pd
from datetime import datetime, timedelta

# Alternative: Connexion directe si get_db_connection échoue
def get_db_connection_direct():
    """Connexion directe à PostgreSQL pour éviter les problèmes d'encodage."""
    import psycopg2
    
    # Utiliser les valeurs directement (éviter os.getenv qui peut avoir des problèmes d'encodage)
    try:
        conn = psycopg2.connect(
            host='africaits.com',
            port=5432,
            database='Traffic_Tracking',
            user='Alidorsabue',
            password='Virgi@1996',
            client_encoding='UTF8',
            connect_timeout=10
        )
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion directe: {e}")
        raise

# Alternative: Connexion directe si get_db_connection échoue
def get_db_connection_direct():
    """Connexion directe à PostgreSQL pour éviter les problèmes d'encodage."""
    import psycopg2
    
    # Utiliser les valeurs directement (éviter os.getenv qui peut avoir des problèmes d'encodage)
    # Ces valeurs peuvent être modifiées si nécessaire
    try:
        conn = psycopg2.connect(
            host='africaits.com',
            port=5432,
            database='Traffic_Tracking',
            user='Alidorsabue',
            password='Virgi@1996',
            client_encoding='UTF8',
            connect_timeout=10
        )
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion directe: {e}")
        raise

def check_table_data(table_name, query=None, use_direct=False):
    """Vérifie si une table contient des données."""
    conn = None
    try:
        # Essayer d'abord get_db_connection, puis connexion directe si échec
        if use_direct:
            conn = get_db_connection_direct()
        else:
            try:
                conn = get_db_connection()
            except (UnicodeDecodeError, UnicodeError) as e:
                print(f"[WARNING] Problème d'encodage avec get_db_connection(), utilisation de la connexion directe...")
                conn = get_db_connection_direct()
    except Exception as e:
        print(f"[ERROR] ERREUR lors de la connexion à la base de données: {e}")
        return {
            'exists': False,
            'error': str(e),
            'has_data': False,
            'connection_error': True
        }
    
    try:
        if query:
            df = pd.read_sql(query, conn)
        else:
            df = pd.read_sql(f"SELECT * FROM {table_name} LIMIT 10", conn)
        
        total_count = pd.read_sql(f"SELECT COUNT(*) as count FROM {table_name}", conn)['count'].iloc[0]
        
        return {
            'exists': True,
            'total_rows': int(total_count),
            'sample_data': df,
            'has_data': total_count > 0
        }
    except Exception as e:
        return {
            'exists': False,
            'error': str(e),
            'has_data': False
        }
    finally:
        conn.close()

def diagnostic_complete():
    """Effectue un diagnostic complet de toutes les tables."""
    print("=" * 80)
    print("DIAGNOSTIC DES TABLES - TRAFFIC TRACKING PIPELINE")
    print("=" * 80)
    print(f"Date du diagnostic: {datetime.now()}\n")
    
    # Test de connexion d'abord
    print("[INFO] Test de connexion à la base de données...")
    try:
        test_conn = get_db_connection()
        test_conn.close()
        print("[SUCCESS] Connexion réussie avec get_db_connection()\n")
        use_direct = False
    except (UnicodeDecodeError, UnicodeError) as e:
        print(f"[WARNING] Problème d'encodage détecté, utilisation de la connexion directe...")
        try:
            test_conn = get_db_connection_direct()
            test_conn.close()
            print("[SUCCESS] Connexion réussie avec connexion directe\n")
            use_direct = True
        except Exception as e2:
            print(f"[ERROR] Impossible de se connecter à la base de données: {e2}")
            print("\nVérifier:")
            print("  1. Que le serveur PostgreSQL est accessible (africaits.com:5432)")
            print("  2. Que les credentials sont corrects")
            print("  3. Que le pare-feu permet la connexion")
            return None
    except Exception as e:
        print(f"[ERROR] Erreur de connexion: {e}")
        return None
    
    results = {}
    
    # 1. Vérifier gps_points (SOURCE DE DONNÉES)
    print("\n[1] VÉRIFICATION DE gps_points (SOURCE)")
    print("-" * 80)
    query_recent = """
        SELECT COUNT(*) as count,
               MIN(timestamp) as oldest,
               MAX(timestamp) as newest
        FROM gps_points
    """
    gps_check = check_table_data('gps_points', query_recent, use_direct=use_direct)
    results['gps_points'] = gps_check
    
    if gps_check.get('exists'):
        print(f"[SUCCESS] Table gps_points existe")
        if gps_check['has_data']:
            print(f"[SUCCESS] {gps_check['total_rows']} lignes au total")
            gps_details = gps_check['sample_data']
            if not gps_details.empty and 'oldest' in gps_details.columns:
                print(f"   Plus ancienne donnée: {gps_details['oldest'].iloc[0]}")
                print(f"   Plus récente donnée: {gps_details['newest'].iloc[0]}")
        else:
            print(f"[ERROR] Table gps_points est VIDE")
            print(f"   [WARNING] PROBLÈME: L'app mobile n'envoie pas de données ou la connexion DB ne fonctionne pas")
    else:
        print(f"[ERROR] Table gps_points n'existe pas: {gps_check.get('error')}")
    
    # 2. Vérifier mapmatching_cache
    print("\n[2] VÉRIFICATION DE mapmatching_cache")
    print("-" * 80)
    query_cache_recent = """
        SELECT COUNT(*) as count,
               MIN(processed_at) as oldest_processed,
               MAX(processed_at) as newest_processed,
               COUNT(CASE WHEN edge_u IS NOT NULL THEN 1 END) as matched_count
        FROM mapmatching_cache
        WHERE processed_at > NOW() - INTERVAL '2 hours'
    """
    cache_check = check_table_data('mapmatching_cache', query_cache_recent, use_direct=use_direct)
    results['mapmatching_cache'] = cache_check
    
    if cache_check.get('exists'):
        print(f"[SUCCESS] Table mapmatching_cache existe")
        if cache_check['has_data']:
            cache_details = cache_check['sample_data']
            if not cache_details.empty:
                total_recent = cache_details['count'].iloc[0] if 'count' in cache_details.columns else 0
                matched = cache_details['matched_count'].iloc[0] if 'matched_count' in cache_details.columns else 0
                print(f"[SUCCESS] {total_recent} entrées dans les 2 dernières heures")
                print(f"   {matched} points matchés ({matched/total_recent*100:.1f}%)" if total_recent > 0 else "   0% matchés")
                if 'newest_processed' in cache_details.columns:
                    print(f"   Dernière mise à jour: {cache_details['newest_processed'].iloc[0]}")
        else:
            print(f"[ERROR] Table mapmatching_cache est VIDE ou aucune donnée récente")
            print(f"   [WARNING] PROBLÈME: Le DAG 'mapmatching_cache_hourly' ne s'exécute pas ou échoue")
            print(f"   Solution: Vérifier que le DAG mapmatching_cache_hourly s'exécute toutes les heures")
    else:
        print(f"[ERROR] Table mapmatching_cache n'existe pas: {cache_check.get('error')}")
    
    # 3. Vérifier edge_agg
    print("\n[3] VÉRIFICATION DE edge_agg")
    print("-" * 80)
    query_edge_recent = """
        SELECT COUNT(*) as count,
               MIN(ts) as oldest,
               MAX(ts) as newest
        FROM edge_agg
        WHERE ts > NOW() - INTERVAL '24 hours'
    """
    edge_check = check_table_data('edge_agg', query_edge_recent, use_direct=use_direct)
    results['edge_agg'] = edge_check
    
    if edge_check.get('exists'):
        print(f"[SUCCESS] Table edge_agg existe")
        if edge_check['has_data']:
            edge_details = edge_check['sample_data']
            if not edge_details.empty:
                recent_count = edge_details['count'].iloc[0] if 'count' in edge_details.columns else 0
                print(f"[SUCCESS] {recent_count} lignes dans les 24 dernières heures")
                total_edge = check_table_data('edge_agg', "SELECT COUNT(*) as count FROM edge_agg")['total_rows']
                print(f"   Total: {total_edge} lignes")
        else:
            print(f"[ERROR] Table edge_agg est VIDE ou aucune donnée récente")
            print(f"   [WARNING] PROBLÈME: Le DAG 'traffic_advanced_analysis' ne peut pas charger de données")
            print(f"   Causes possibles:")
            print(f"     - mapmatching_cache est vide")
            print(f"     - Les données GPS ne peuvent pas être matchées à des routes")
            print(f"     - Le DAG traffic_advanced_analysis échoue")
    else:
        print(f"[ERROR] Table edge_agg n'existe pas: {edge_check.get('error')}")
    
    # 4. Vérifier predictions
    print("\n[4] VÉRIFICATION DE predictions")
    print("-" * 80)
    query_pred_recent = """
        SELECT COUNT(*) as count,
               MIN(ts) as oldest,
               MAX(ts) as newest
        FROM predictions
        WHERE ts > NOW() - INTERVAL '24 hours'
    """
    pred_check = check_table_data('predictions', query_pred_recent, use_direct=use_direct)
    results['predictions'] = pred_check
    
    if pred_check.get('exists'):
        print(f"[SUCCESS] Table predictions existe")
        if pred_check['has_data']:
            pred_details = pred_check['sample_data']
            if not pred_details.empty:
                recent_count = pred_details['count'].iloc[0] if 'count' in pred_details.columns else 0
                print(f"[SUCCESS] {recent_count} prédictions dans les 24 dernières heures")
        else:
            print(f"[ERROR] Table predictions est VIDE")
            print(f"   [WARNING] PROBLÈME: Le modèle ML ne peut pas générer de prédictions")
            print(f"   Causes possibles:")
            print(f"     - edge_agg est vide (pas de données pour entraîner/prédire)")
            print(f"     - Le modèle ML échoue lors de l'entraînement ou de la prédiction")
    else:
        print(f"[ERROR] Table predictions n'existe pas: {pred_check.get('error')}")
    
    # 5. Vérifier edge_hourly_baseline
    print("\n[5] VÉRIFICATION DE edge_hourly_baseline")
    print("-" * 80)
    baseline_check = check_table_data('edge_hourly_baseline', "SELECT COUNT(*) as count FROM edge_hourly_baseline", use_direct=use_direct)
    results['edge_hourly_baseline'] = baseline_check
    
    if baseline_check.get('exists'):
        print(f"[SUCCESS] Table edge_hourly_baseline existe")
        if baseline_check['has_data']:
            print(f"[SUCCESS] {baseline_check['total_rows']} lignes de baseline")
            query_baseline_details = """
                SELECT COUNT(DISTINCT edge_u || '-' || edge_v) as unique_edges,
                       COUNT(DISTINCT hour) as unique_hours
                FROM edge_hourly_baseline
            """
            try:
                conn = get_db_connection()
                details = pd.read_sql(query_baseline_details, conn)
                conn.close()
                if not details.empty:
                    print(f"   {details['unique_edges'].iloc[0]} tronçons uniques")
                    print(f"   {details['unique_hours'].iloc[0]} heures couvertes")
            except:
                pass
        else:
            print(f"❌ Table edge_hourly_baseline est VIDE")
            print(f"   ⚠️  PROBLÈME: Le DAG 'compute_baseline_daily' ne peut pas calculer la baseline")
            print(f"   Causes possibles:")
            print(f"     - edge_agg est vide (pas de données historiques)")
            print(f"     - Le DAG compute_baseline_daily ne s'exécute pas ou échoue")
    else:
        print(f"❌ Table edge_hourly_baseline n'existe pas: {baseline_check.get('error')}")
    
    # Résumé et recommandations
    print("\n" + "=" * 80)
    print("RÉSUMÉ ET RECOMMANDATIONS")
    print("=" * 80)
    
    issues = []
    
    if not results.get('gps_points', {}).get('has_data'):
        issues.append("🔴 CRITIQUE: gps_points est vide - Vérifier que l'app mobile envoie des données")
        issues.append("   Action: Vérifier la connexion à la base de données depuis l'app mobile")
    
    if not results.get('mapmatching_cache', {}).get('has_data'):
        issues.append("🔴 CRITIQUE: mapmatching_cache est vide - Le DAG mapmatching_cache_hourly doit s'exécuter")
        issues.append("   Action: Vérifier dans Airflow que le DAG 'mapmatching_cache_hourly' s'exécute toutes les heures")
    
    if not results.get('edge_agg', {}).get('has_data'):
        issues.append("🟡 WARNING: edge_agg est vide - Dépend de mapmatching_cache")
        issues.append("   Action: Résoudre d'abord le problème de mapmatching_cache")
    
    if not results.get('predictions', {}).get('has_data'):
        issues.append("🟡 WARNING: predictions est vide - Dépend de edge_agg")
        issues.append("   Action: Résoudre d'abord le problème de edge_agg")
    
    if not results.get('edge_hourly_baseline', {}).get('has_data'):
        issues.append("🟡 WARNING: edge_hourly_baseline est vide - Dépend de edge_agg")
        issues.append("   Action: Résoudre d'abord le problème de edge_agg, puis exécuter compute_baseline_daily")
    
    if issues:
        print("\nProblèmes détectés:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("\n✅ Toutes les tables contiennent des données!")
    
    print("\n" + "=" * 80)
    return results

if __name__ == "__main__":
    diagnostic_complete()


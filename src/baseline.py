# src/baseline.py
"""
Module pour calculer une baseline horaire de vitesse moyenne par tronçon de route.
Cette baseline utilise la médiane des vitesses historiques pour chaque heure de la journée.
"""
import pandas as pd
from sqlalchemy import create_engine
import os

# Fonction pour obtenir l'URI SQLAlchemy
def get_db_uri():
    """
    Crée une URI SQLAlchemy en utilisant les variables d'environnement.
    - En production: utilise africaits.com par défaut
    - En local: utilise localhost
    """
    # Récupérer les valeurs depuis les variables d'environnement
    host = os.getenv('POSTGRES_HOST', 'africaits.com')
    port = os.getenv('POSTGRES_PORT', '5432')
    database = os.getenv('POSTGRES_DB', 'Traffic_Tracking')
    user = os.getenv('POSTGRES_USER', 'Alidorsabue')
    password = os.getenv('POSTGRES_PASSWORD', 'Virgi@1996')
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

# Configuration de la base de données PostgreSQL
DB_URI = get_db_uri()
engine = create_engine(DB_URI)

def compute_hourly_baseline(history_days=None, min_days=1):
    """
    Calcule une baseline horaire (médiane) de vitesse moyenne par tronçon.
    Utilise automatiquement tous les jours disponibles si history_days n'est pas spécifié.
    
    Parameters:
    -----------
    history_days : int, optional
        Nombre de jours d'historique à utiliser (par défaut: None = utilise tous les jours disponibles)
    min_days : int
        Nombre minimum de jours requis pour calculer la baseline (par défaut: 1 jour)
    
    Returns:
    --------
    pandas.DataFrame or None
        DataFrame avec les colonnes edge_u, edge_v, hour, baseline_kmh
        ou None en cas d'erreur
    """
    try:
        # Si history_days n'est pas spécifié, détecter automatiquement les jours disponibles
        if history_days is None:
            # Compter les jours disponibles dans edge_agg
            check_sql = """
                SELECT 
                    DATE(ts) as date_only,
                    COUNT(*) as count
                FROM edge_agg
                GROUP BY DATE(ts)
                ORDER BY date_only DESC;
            """
            try:
                dates_df = pd.read_sql(check_sql, engine)
                if dates_df.empty:
                    print("Aucune donnée disponible dans edge_agg")
                    return None
                
                available_days = dates_df['date_only'].nunique()
                # Utiliser tous les jours disponibles + 1 jour de marge
                history_days = max(available_days + 1, min_days)
                print(f"Détection automatique: {available_days} jours de données disponibles, utilisation de {history_days} jours")
            except Exception as e:
                print(f"Erreur lors de la détection des jours disponibles: {e}")
                # En cas d'erreur, utiliser une valeur par défaut
                history_days = 30
                print(f"Utilisation de la valeur par défaut: {history_days} jours")
        else:
            # Vérifier que history_days est valide
            if history_days < min_days:
                print(f"Attention: history_days ({history_days}) est inférieur au minimum requis ({min_days} jours)")
                print(f"   Le calcul sera effectué avec les données disponibles")
        
        # Vérifier que history_days est positif
        if history_days <= 0:
            print(f"Erreur: history_days doit être positif (reçu: {history_days})")
            return None
        
        sql = f"""
          SELECT edge_u, edge_v, ts, avg_speed_kmh
          FROM edge_agg
          WHERE ts >= NOW() - INTERVAL '{history_days} days';
        """
        
        df = pd.read_sql(sql, engine)
        
        # Vérifier si des données existent
        if df.empty:
            print(f"Aucune donnée disponible pour la baseline (table edge_agg vide ou inexistante)")
            print(f"   Vérifier que la table edge_agg contient des données récentes")
            return None
        
        # Vérifier que les colonnes nécessaires existent
        required_cols = ['edge_u', 'edge_v', 'ts', 'avg_speed_kmh']
        if not all(col in df.columns for col in required_cols):
            missing = set(required_cols) - set(df.columns)
            print(f"Erreur: Colonnes manquantes dans la table edge_agg: {missing}")
            return None
        
        # S'assurer que 'ts' est de type datetime
        if not pd.api.types.is_datetime64_any_dtype(df['ts']):
            df['ts'] = pd.to_datetime(df['ts'])
        
        # Créer la colonne hour
        df['hour'] = df['ts'].dt.hour
        
        # Informations sur les données disponibles
        days_covered = (df['ts'].max() - df['ts'].min()).days + 1 if len(df) > 0 else 0
        print(f"Données récupérées: {len(df)} lignes couvrant {days_covered} jour(s)")
        print(f"   Période: {df['ts'].min()} à {df['ts'].max()}")
        
        # Calculer la médiane par tronçon et par heure
        baseline = df.groupby(['edge_u', 'edge_v', 'hour'])['avg_speed_kmh']\
                     .median().reset_index().rename(columns={'avg_speed_kmh': 'baseline_kmh'})
        
        # Vérifier que le résultat n'est pas vide
        if baseline.empty:
            print("Aucune baseline calculee (donnees insuffisantes)")
            print("   Assurez-vous que edge_agg contient des données avec edge_u, edge_v et avg_speed_kmh")
            return None
        
        # Avertissement si peu de données
        if days_covered < 7:
            print(f"ATTENTION: Baseline calculee avec seulement {days_covered} jour(s) de données")
            print(f"   La baseline sera moins precise qu'avec 30 jours d'historique")
            print(f"   Elle sera automatiquement mise a jour au fur et a mesure que les donnees s'accumulent")
        elif days_covered < 30:
            print(f"INFO: Baseline calculee avec {days_covered} jour(s) de données (objectif: 30 jours)")
        
        # Sauvegarder dans la base de données
        try:
            baseline.to_sql('edge_hourly_baseline', engine, if_exists='replace', index=False)
            print(f"Baseline horaire calculee et sauvegardee ({len(baseline)} lignes)")
            print(f"   Tronçons couverts: {baseline['edge_u'].nunique()}")
            print(f"   Heures couvertes: {sorted(baseline['hour'].unique())}")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde de la baseline : {e}")
            print("   Les données sont retournées sans être sauvegardées")
        
        return baseline
        
    except Exception as e:
        print(f"Erreur lors du calcul de la baseline : {e}")
        import traceback
        traceback.print_exc()
        return None

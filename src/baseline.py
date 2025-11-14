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

def compute_hourly_baseline(history_days=30):
    """
    Calcule une baseline horaire (médiane) de vitesse moyenne par tronçon.
    
    Parameters:
    -----------
    history_days : int
        Nombre de jours d'historique à utiliser (par défaut: 30)
    
    Returns:
    --------
    pandas.DataFrame or None
        DataFrame avec les colonnes edge_u, edge_v, hour, baseline_kmh
        ou None en cas d'erreur
    """
    try:
        # Vérifier que history_days est valide
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
        
        # Calculer la médiane par tronçon et par heure
        baseline = df.groupby(['edge_u', 'edge_v', 'hour'])['avg_speed_kmh']\
                     .median().reset_index().rename(columns={'avg_speed_kmh': 'baseline_kmh'})
        
        # Vérifier que le résultat n'est pas vide
        if baseline.empty:
            print("Aucune baseline calculee (donnees insuffisantes)")
            return None
        
        # Sauvegarder dans la base de données
        try:
            baseline.to_sql('edge_hourly_baseline', engine, if_exists='replace', index=False)
            print(f"Baseline horaire calculee et sauvegardee ({len(baseline)} lignes)")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde de la baseline : {e}")
            print("   Les données sont retournées sans être sauvegardées")
        
        return baseline
        
    except Exception as e:
        print(f"Erreur lors du calcul de la baseline : {e}")
        import traceback
        traceback.print_exc()
        return None

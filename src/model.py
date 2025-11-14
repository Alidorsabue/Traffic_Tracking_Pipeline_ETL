# Objectif :
#   - Extraire les données de vitesse agrégées depuis PostgreSQL
#   - Créer les variables de décalage temporel (lags)
#   - Entraîner un modèle Random Forest pour prédire la vitesse future
#   - Sauvegarder le modèle pour usage ultérieur (prédiction automatique)       

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import joblib
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

# Fonction : prepare_features()
#   - Créer des variables dérivées (lags, heure, jour de la semaine)
#   - Trier les données temporellement par tronçon (edge)

def prepare_features(edge_agg_df, lags=[1, 2, 3, 4, 5, 6]):
    """
    Prépare les features pour l'entraînement du modèle.
    
    Parameters:
    -----------
    edge_agg_df : pandas.DataFrame
        DataFrame avec les colonnes edge_u, edge_v, ts, avg_speed_kmh
    lags : list
        Liste des décalages temporels à créer
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame avec les features préparées
    """
    # Gérer le cas où le DataFrame est vide
    if edge_agg_df.empty:
        return pd.DataFrame()
    
    df = edge_agg_df.copy()

    # Vérifier que les colonnes nécessaires existent
    required_cols = ['edge_u', 'edge_v', 'ts', 'avg_speed_kmh']
    if not all(col in df.columns for col in required_cols):
        print(f"Erreur: Le DataFrame doit contenir les colonnes: {required_cols}")
        return pd.DataFrame()

    # S'assurer que 'ts' est de type datetime
    if not pd.api.types.is_datetime64_any_dtype(df['ts']):
        df['ts'] = pd.to_datetime(df['ts'])

    # Tri chronologique des observations par tronçon
    df = df.sort_values(['edge_u', 'edge_v', 'ts'])

    # Création des variables "lag" : vitesses passées sur le même tronçon       
    for lag in lags:
        df[f'lag_{lag}'] = df.groupby(['edge_u', 'edge_v'])['avg_speed_kmh'].shift(lag)                                                                         

    # Variables temporelles explicatives
    df['hour'] = df['ts'].dt.hour        # Heure de la journée (0–23)
    df['weekday'] = df['ts'].dt.weekday  # Jour de la semaine (0 = lundi)       

    # Suppression des lignes avec valeurs manquantes (causées par les lags)     
    df = df.dropna()

    return df

# Fonction : train_model()
#   - Extraire les données récentes (30 derniers jours)
#   - Préparer les features et la cible
#   - Entraîner un modèle Random Forest
#   - Sauvegarder le modèle entraîné

def train_model():
    """
    Entraîne un modèle Random Forest pour prédire la vitesse future.
    
    Returns:
    --------
    sklearn.ensemble.RandomForestRegressor or None
        Modèle entraîné ou None en cas d'erreur
    """
    try:
        # Extraction des données sur les 30 derniers jours
        # Note: Si la table edge_agg n'existe pas, cette fonction échouera
        # Il faudra créer cette table à partir des données de congestion ou gps_points
        sql = "SELECT * FROM edge_agg WHERE ts >= NOW() - INTERVAL '30 days';"      
        df = pd.read_sql(sql, engine)

        # Vérifier si des données existent
        if df.empty:
            print("Aucune donnée disponible pour l'entraînement (table edge_agg vide ou inexistante)")
            return None

        # Préparation des variables explicatives
        df_feat = prepare_features(df)
        
        if df_feat.empty:
            print("Aucune feature préparée (probablement pas assez de données historiques)")
            return None

        # La cible (y) correspond à la vitesse du pas de temps suivant
        df_feat['y'] = df_feat.groupby(['edge_u', 'edge_v'])['avg_speed_kmh'].shift(-1)                                                                             

        # Suppression des lignes incomplètes
        df_feat = df_feat.dropna()

        if df_feat.empty:
            print("Aucune donnée complète après préparation")
            return None

        # Sélection des variables explicatives
        feature_cols = [c for c in df_feat.columns if c.startswith('lag_')] + ['hour', 'weekday']
        if not all(col in df_feat.columns for col in feature_cols):
            print(f"Erreur: Colonnes manquantes: {set(feature_cols) - set(df_feat.columns)}")
            return None
            
        X = df_feat[feature_cols]
        y = df_feat['y']

        # Découpage train/test (80% / 20%)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Entraînement du modèle Random Forest
        model = RandomForestRegressor(n_estimators=100, n_jobs=-1, random_state=42)
        model.fit(X_train, y_train)

        # Évaluation rapide du modèle
        score = model.score(X_test, y_test)
        print(f"Score R² sur le jeu de test : {score:.4f}")

        # Créer le répertoire models s'il n'existe pas
        models_dir = "models"
        if not os.path.exists(models_dir):
            os.makedirs(models_dir)
            print(f"Repertoire '{models_dir}' cree")

        # Sauvegarde du modèle entraîné
        model_path = os.path.join(models_dir, "rf_edge_speed.pkl")
        joblib.dump(model, model_path)
        print(f"Modèle Random Forest sauvegardé sous : {model_path}")
        
        return model
        
    except Exception as e:
        print(f"Erreur lors de l'entraînement du modèle : {e}")
        import traceback
        traceback.print_exc()
        return None

# Fonction : predict_next()
# Objectif :
#   - Charger le modèle sauvegardé
#   - Préparer les dernières observations pour prédire la vitesse future        

def predict_next():
    """
    Prédit la vitesse future pour les tronçons récents.
    Returns:
    --------
    pandas.DataFrame or None
        DataFrame avec les prédictions ou None en cas d'erreur
    """
    try:
        # Vérifier que le modèle existe
        model_path = os.path.join("models", "rf_edge_speed.pkl")
        if not os.path.exists(model_path):
            print(f"Le modèle n'existe pas : {model_path}")
            print("  Exécutez d'abord train_model() pour entraîner le modèle")
            return None
        
        # Chargement du modèle pré-entraîné
        model = joblib.load(model_path)

        # Extraction des dernières observations (par exemple sur la dernière heure) 
        sql = "SELECT * FROM edge_agg WHERE ts >= NOW() - INTERVAL '1 hour';"       
        df_recent = pd.read_sql(sql, engine)

        if df_recent.empty:
            print("Aucune donnée récente disponible pour la prédiction")
            return pd.DataFrame()

        # Préparation des features à partir des observations récentes
        df_feat = prepare_features(df_recent)
        
        if df_feat.empty:
            print("Impossible de préparer les features pour la prédiction")
            return pd.DataFrame()

        # Sélection des variables explicatives
        feature_cols = [c for c in df_feat.columns if c.startswith('lag_')] + ['hour', 'weekday']
        if not all(col in df_feat.columns for col in feature_cols):
            print(f"Erreur: Colonnes manquantes: {set(feature_cols) - set(df_feat.columns)}")
            return pd.DataFrame()
            
        X_pred = df_feat[feature_cols]

        # Prédiction de la vitesse moyenne pour le prochain intervalle
        df_feat['pred_speed_kmh'] = model.predict(X_pred)

        # Retour du DataFrame avec les prédictions
        print("Prédictions effectuées sur les tronçons récents.")
        return df_feat[['edge_u', 'edge_v', 'ts', 'pred_speed_kmh']]
        
    except Exception as e:
        print(f"Erreur lors de la prédiction : {e}")
        import traceback
        traceback.print_exc()
        return None

# Exemple d'utilisation (hors Airflow) :
# model = train_model()
# if model is not None:
#     df_pred = predict_next()
#     if df_pred is not None and not df_pred.empty:
#         print(df_pred.head())

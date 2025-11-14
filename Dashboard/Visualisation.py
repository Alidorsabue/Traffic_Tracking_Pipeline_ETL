import streamlit as st
import folium
from streamlit_folium import st_folium
import sys
from pathlib import Path
import os
import pandas as pd
import psycopg2

# Ajouter le répertoire racine au PYTHONPATH AVANT tout import de src
# Streamlit peut avoir des problèmes avec __file__, on utilise une méthode plus robuste
try:
    # Essayer avec __file__ d'abord
    script_path = Path(__file__).resolve()
    root_dir = script_path.parent.parent
except NameError:
    # Si __file__ n'existe pas (certains environnements), utiliser le répertoire de travail
    root_dir = Path(os.getcwd())

# S'assurer que root_dir contient le dossier src
if not (root_dir / "src").exists():
    # Si src n'existe pas, essayer le répertoire parent
    root_dir = Path(os.getcwd())

sys.path.insert(0, str(root_dir))

# Importer les modules src APRÈS avoir modifié sys.path
from src.Script_ETL import extract_recent_data, clean_data, detect_congestion, aggregate_by_zone, load_to_db

# Fonction helper pour la connexion à la base de données
def get_db_connection():
    """Crée une connexion PostgreSQL en utilisant les variables d'environnement."""
    # En production, utiliser africaits.com par défaut
    host = os.getenv('POSTGRES_HOST', 'africaits.com')
    port = int(os.getenv('POSTGRES_PORT', '5432'))
    database = os.getenv('POSTGRES_DB', 'Traffic_Tracking')
    user = os.getenv('POSTGRES_USER', 'Alidorsabue')
    password = os.getenv('POSTGRES_PASSWORD', 'Virgi@1996')
    
    return psycopg2.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password
    )

st.title("Dashboard de Trafic - Kinshasa")
st.markdown("### Visualisation en temps réel et prédictions ML")

# Sidebar pour la navigation
st.sidebar.header("Navigation")
view_mode = st.sidebar.radio(
    "Mode d'affichage",
    ["Congestion actuelle", "Prédictions ML", "Comparaison"]
)

# Fonction pour charger les prédictions depuis la base de données
def load_predictions():
    """Charge les prédictions récentes depuis la table predictions."""
    try:
        conn = get_db_connection()
        
        query = """
        SELECT p.edge_u, p.edge_v, p.ts, p.pred_speed_kmh, p.created_at
        FROM predictions p
        WHERE p.ts >= NOW() - INTERVAL '1 hour'
        ORDER BY p.ts DESC
        LIMIT 500
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erreur lors du chargement des prédictions: {e}")
        return pd.DataFrame()

# Fonction pour charger les données edge_agg (vitesses observées) pour comparaison
def load_edge_agg():
    """Charge les vitesses observées récentes depuis edge_agg."""
    try:
        conn = get_db_connection()
        
        query = """
        SELECT edge_u, edge_v, ts, avg_speed_kmh
        FROM edge_agg
        WHERE ts >= NOW() - INTERVAL '1 hour'
        ORDER BY ts DESC
        LIMIT 500
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erreur lors du chargement des données edge_agg: {e}")
        return pd.DataFrame()

# Fonction pour obtenir les coordonnées géographiques à partir des edge_u et edge_v
# Note: Cette fonction nécessite d'avoir une table avec les coordonnées des nœuds OSM
# Pour l'instant, on utilisera une approche simplifiée avec les données GPS originales
def get_coordinates_for_edges(df_edges, df_gps):
    """Associe les coordonnées géographiques aux edges en utilisant les données GPS."""
    # Cette fonction est une simplification - dans un cas réel, on devrait
    # avoir une table avec les coordonnées des nœuds OSM
    # Pour l'instant, on retourne les données sans coordonnées
    return df_edges

# Vue: Congestion actuelle
if view_mode == "Congestion actuelle":
    st.header("Etat actuel de la congestion")
    
    # Lire les données avec gestion d'erreur
    try:
        df = extract_recent_data()
        
        # Si pas de données récentes, charger toutes les données disponibles
        if df.empty:
            st.info("Aucune donnee recente (30 dernieres minutes). Chargement de toutes les donnees disponibles...")
            conn = get_db_connection()
            
            query_all = """
            SELECT driver_id, latitude, longitude, speed, timestamp
            FROM gps_points
            ORDER BY timestamp DESC
            LIMIT 1000
            """
            
            df = pd.read_sql(query_all, conn)
            conn.close()
            
            if df.empty:
                st.error("Aucune donnee disponible dans la base de donnees.")
                st.info("Vérifiez que votre application mobile envoie bien des données à PostgreSQL.")
                st.stop()
            else:
                st.success(f"{len(df)} enregistrements charges")
        
        # Nettoyage et détection de congestion
        df = clean_data(df)
        df = detect_congestion(df)
        
        # Statistiques
        st.sidebar.header("Statistiques")
        st.sidebar.metric("Total de points", len(df))
        st.sidebar.metric("Points congestionnés", int(df['is_congested'].sum()))
        if len(df) > 0:
            st.sidebar.metric("Taux de congestion", f"{df['is_congested'].mean()*100:.1f}%")
            st.sidebar.metric("Vitesse moyenne", f"{df['speed'].mean():.2f} km/h")
        
        # Carte de Kinshasa
        m = folium.Map(location=[-4.325, 15.31], zoom_start=12)
        
        # Ajouter les points congestionnés
        congested = df[df['is_congested']]
        if not congested.empty:
            for _, row in congested.iterrows():
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=5,
                    color='red',
                    fill=True,
                    fill_opacity=0.7,
                    popup=f"Vitesse: {row['speed']:.2f} km/h<br>Heure: {row['timestamp']}"
                ).add_to(m)
        
        # Ajouter les points normaux en vert (optionnel, limité pour la performance)
        normal = df[~df['is_congested']]
        if not normal.empty and len(normal) <= 100:
            for _, row in normal.head(100).iterrows():
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=3,
                    color='green',
                    fill=True,
                    fill_opacity=0.3,
                    popup=f"Vitesse: {row['speed']:.2f} km/h"
                ).add_to(m)
        
        # Afficher la carte
        st_folium(m, width=700, height=500)
        
    except Exception as e:
        st.error(f"Erreur lors du chargement des donnees: {e}")
        st.info("Vérifiez la connexion à PostgreSQL (port 5433) et que les tables existent.")

# Vue: Prédictions ML
elif view_mode == "Prédictions ML":
    st.header("Predictions de vitesse (Machine Learning)")
    st.info("Les predictions sont basees sur un modele Random Forest entraine sur les donnees historiques.")
    
    df_pred = load_predictions()
    
    if df_pred.empty:
        st.warning("Aucune prediction disponible pour le moment.")
        st.info("""
        Les prédictions nécessitent :
        1. Des données dans la table `edge_agg`
        2. Un modèle entraîné (dans `models/rf_edge_speed.pkl`)
        3. L'exécution des tâches ML dans le DAG Airflow
        """)
    else:
        st.success(f"{len(df_pred)} predictions chargees")
        
        # Statistiques des prédictions
        st.sidebar.header("Statistiques des prédictions")
        st.sidebar.metric("Nombre de prédictions", len(df_pred))
        st.sidebar.metric("Vitesse moyenne prédite", f"{df_pred['pred_speed_kmh'].mean():.2f} km/h")
        st.sidebar.metric("Vitesse min prédite", f"{df_pred['pred_speed_kmh'].min():.2f} km/h")
        st.sidebar.metric("Vitesse max prédite", f"{df_pred['pred_speed_kmh'].max():.2f} km/h")
        
        # Afficher un tableau des prédictions
        st.subheader("Tableau des prédictions")
        st.dataframe(df_pred.head(20))
        
        # Histogramme des vitesses prédites
        st.subheader("Distribution des vitesses prédites")
        st.bar_chart(df_pred['pred_speed_kmh'])
        
        st.info("Note: Pour visualiser les predictions sur la carte, il faut associer les edges (edge_u, edge_v) aux coordonnees geographiques via les noeuds OSM.")

# Vue: Comparaison
elif view_mode == "Comparaison":
    st.header("Comparaison : Observe vs Predict")
    
    df_obs = load_edge_agg()
    df_pred = load_predictions()
    
    if df_obs.empty and df_pred.empty:
        st.warning("Aucune donnee disponible pour la comparaison.")
    elif df_obs.empty:
        st.warning("Aucune donnee observee disponible.")
        st.info("Les donnees observees sont dans la table `edge_agg`.")
    elif df_pred.empty:
        st.warning("Aucune prediction disponible.")
        st.info("Les predictions sont generees par le modele ML dans la table `predictions`.")
    else:
        # Fusionner les données pour comparaison
        df_merged = pd.merge(
            df_obs,
            df_pred,
            on=['edge_u', 'edge_v', 'ts'],
            how='inner',
            suffixes=('_obs', '_pred')
        )
        
        if df_merged.empty:
            st.warning("Aucune correspondance entre les donnees observees et les predictions pour la meme periode.")
        else:
            st.success(f"{len(df_merged)} correspondances trouvees")
            
            # Calculer l'erreur de prédiction
            df_merged['error'] = df_merged['avg_speed_kmh'] - df_merged['pred_speed_kmh']
            df_merged['abs_error'] = df_merged['error'].abs()
            
            # Métriques de performance
            mae = df_merged['abs_error'].mean()
            rmse = (df_merged['error'] ** 2).mean() ** 0.5
            
            st.sidebar.header("Métriques de performance")
            st.sidebar.metric("MAE (Erreur moyenne absolue)", f"{mae:.2f} km/h")
            st.sidebar.metric("RMSE (Racine de l'erreur quadratique)", f"{rmse:.2f} km/h")
            
            # Graphique de comparaison
            st.subheader("Comparaison des vitesses")
            st.line_chart(df_merged[['avg_speed_kmh', 'pred_speed_kmh']].head(50))
            
            # Distribution des erreurs
            st.subheader("Distribution des erreurs de prédiction")
            st.bar_chart(df_merged['error'])
            
            # Tableau de comparaison
            st.subheader("Détails de la comparaison")
            st.dataframe(df_merged[['edge_u', 'edge_v', 'ts', 'avg_speed_kmh', 'pred_speed_kmh', 'error']].head(20))

# Système de Suivi et Prédiction du Trafic - Kinshasa

## Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture du système](#architecture-du-système)
3. [Prérequis et installation](#prérequis-et-installation)
4. [Configuration](#configuration)
5. [Structure du projet](#structure-du-projet)
6. [Pipeline ETL détaillé](#pipeline-etl-détaillé)
7. [Composants principaux](#composants-principaux)
8. [Base de données](#base-de-données)
9. [Machine Learning](#machine-learning)
10. [Système d'alertes](#système-dalertes)
11. [Utilisation](#utilisation)
12. [Monitoring et logs](#monitoring-et-logs)
13. [Troubleshooting](#troubleshooting)

---

## Vue d'ensemble

Ce projet est un **pipeline ETL (Extract, Transform, Load)** complet pour la détection de congestion routière, la prédiction de trafic et l'envoi d'alertes en temps réel aux chauffeurs via WhatsApp. Le système est conçu pour la ville de **Kinshasa, République Démocratique du Congo**.

### Fonctionnalités principales

- **Collecte de données GPS et vitesse** en temps réel depuis les  à travers une application mobile que j'ai développé "Traffic tracker app"
- **Map matching** : Association des points GPS aux tronçons routiers (OSM)
- **Détection de congestion** basée sur l'analyse de vitesse
- **Prédiction ML** : Prédiction de la vitesse future avec Random Forest
- **Alertes WhatsApp** : Notifications automatiques aux chauffeurs avec routes alternatives
- **Dashboard** : Visualisation en temps réel avec Streamlit

---

## Architecture du système

```
┌─────────────────────────────────────────────────────────────────┐
│                  Sources de données (App mobile)                │
│                    (GPS points des véhicules)                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PostgreSQL Database                        │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐             │
│  │ gps_points  │  │ edge_agg    │  │ predictions  │             │
│  │ congestion  │  │ baseline    │  │ drivers_reg  │             │
│  └─────────────┘  └─────────────┘  └──────────────┘             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Apache Airflow (DAG)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Extract → Clean → MapMatching → Detect → Aggregate    │   │
│  │  → Load → Predict → Send Alerts                        │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌─────────────────────┐              ┌─────────────────────┐
│   Dashboard         │              │   Alert System     │
│   (Streamlit)       │              │   (WhatsApp/Twilio) │
└─────────────────────┘              └─────────────────────┘
```

### Technologies utilisées

- **Orchestration** : Apache Airflow 2.7.1
- **Base de données** : PostgreSQL 18
- **Containerisation** : Docker & Docker Compose
- **Map Matching** : OSMnx + GeoPandas
- **Machine Learning** : Scikit-learn (Random Forest)
- **Visualisation** : Streamlit + Folium
- **Alertes** : Twilio (WhatsApp API)
- **Langage** : Python 3.13

---

## Prérequis et installation

### Prérequis

- **Docker Desktop** (version 28.0.4 ou supérieure)
- **Git** (pour cloner le repository)
- **Python 3.8+** (pour développement local)
- **PostgreSQL** (si exécution locale sans Docker)

### Installation

1. **Cloner le repository**
```bash
git clone <repository-url>
cd Traffic_tracking_Pipiline_ETL
```

2. **Démarrer les services avec Docker Compose**
```bash
docker-compose up -d
```

Cette commande démarre :
- **PostgreSQL** sur le port `5432` (production : `africaits.com`)
- **Airflow** sur le port `8081`

3. **Accéder à l'interface Airflow**
- URL : http://localhost:8081 (local) ou http://africaits.com:8081 (production)

4. **Initialiser la base de données** (si nécessaire)
```bash
# En production
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -f init_database.sql

# En local
psql -h localhost -p 5433 -U postgres -d Traffic_Tracking -f init_database.sql
```

---

## Configuration

### Variables d'environnement

Le système utilise plusieurs variables d'environnement pour la configuration :

#### Configuration Twilio (Alertes WhatsApp)

```bash
export TWILIO_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token"
export TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886"
```

#### Paramètres d'alerte

```bash
export ALERT_THRESHOLD="0.6"      # Seuil d'indice de congestion (0.0 à 1.0)
export DEBOUNCE_MIN="900"         # Délai minimum entre alertes (secondes, défaut: 15 min)
```

### Configuration Docker

Le fichier `docker-compose.yml` configure :
- **PostgreSQL** : Port 5432 (production : `africaits.com`), utilisateur `Alidorsabue`, base `Traffic_Tracking`
- **Airflow** : Port 8081, LocalExecutor, timeout 120s
- **Volumes** : Montage des dossiers `dags/`, `src/`, `logs/`, `models/`

**Note** : En production, la base de données PostgreSQL est hébergée sur le serveur `africaits.com` (alidor-server). Utilisez `docker-compose.prod.yml` pour le déploiement en production.

---

## Structure du projet

```
Traffic_tracking_Pipiline_ETL/
│
├── dags/                          # DAGs Airflow
│   └── Dags.py                    # DAG principal d'orchestration
│
├── src/                           # Code source Python
│   ├── Script_ETL.py              # Fonctions ETL principales
│   ├── mapmatching.py             # Map matching avec OSMnx
│   ├── model.py                   # Machine Learning (Random Forest)
│   ├── baseline.py                # Calcul des baselines de vitesse
│   ├── alert.py                   # Système d'alertes WhatsApp
│   └── alert_api.py               # API Flask pour alertes
│
├── Dashboard/                     # Interface de visualisation
│   └── Visualisation.py            # Dashboard Streamlit
│
├── models/                        # Modèles ML sauvegardés
│   └── rf_edge_speed.pkl          # Modèle Random Forest
│
├── logs/                          # Logs Airflow
│   └── dag_id=congestion_etl_modular/
│
├── cache/                         # Cache OSMnx (réseau routier)
│
├── docker-compose.yml              # Configuration Docker
├── init_database.sql              # Script d'initialisation DB
├── requirements.txt               # Dépendances Python (général)
├── requirements-airflow.txt       # Dépendances Python (Airflow)
└── README.md                      # Ce fichier
```

---

## Pipeline ETL détaillé

### Vue d'ensemble du flux

Le pipeline s'exécute **toutes les 10 minutes** et suit ce flux :

```
┌─────────────┐
│  Extract    │ → Extraction des données GPS récentes (30 dernières minutes)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Clean     │ → Nettoyage (doublons, vitesses aberrantes > 150 km/h)
└──────┬──────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐   ┌──────────────┐
│ MapMatching │   │   Detect     │ → Détection de congestion
└──────┬──────┘   └──────┬───────┘
       │                 │
       ▼                 ▼
┌─────────────┐   ┌──────────────┐
│ Aggregate   │   │  Aggregate   │ → Agrégation par zone
│   (Edge)    │   │   (Zone)     │
└──────┬──────┘   └──────┬───────┘
       │                 │
       ▼                 ▼
┌─────────────┐   ┌──────────────┐
│ Load Edge   │   │ Load Congest │ → Chargement en base
└──────┬──────┘   └──────┬───────┘
       │                 │
       ▼                 │
┌─────────────┐          │
│ Train/      │          │
│ Predict     │          │
└──────┬──────┘          │
       │                 │
       ▼                 ▼
┌─────────────┐      ┌──────────────┐
│ Load Pred  │      │  Send Alerts │ → Alertes WhatsApp
└────────────┘      └──────────────┘
```

### Étapes détaillées

#### 1. **Extract** (`extract_data`)
- **Fréquence** : Toutes les 10 minutes
- **Source** : Table `gps_points`
- **Période** : Dernières 30 minutes
- **Limite** : 1000 points GPS
- **Données** : `driver_id`, `latitude`, `longitude`, `speed`, `timestamp`

#### 2. **Clean** (`clean_data`)
- **Suppression des doublons**
- **Filtrage** : Vitesses > 150 km/h (aberrantes)
- **Conservation** : Vitesses entre 0 et 150 km/h (y compris arrêt)
- **Ajout** : Colonne `hour` (heure de la journée)

#### 3. **Map Matching** (`mapmatching`)
- **Technologie** : OSMnx + GeoPandas
- **Distance max** : 50 mètres (rayon de recherche)
- **Limite** : 30 points par exécution (optimisation)
- **Résultat** : Association des points GPS aux tronçons routiers (edge_u, edge_v)
- **Cache** : Réseau routier mis en cache pour performance

#### 4. **Detect Congestion** (`detect_congestion`)
- **Méthode** : Analyse de vitesse selon l'heure
- **Seuils** :
  - Heures de pointe (6h-9h, 16h-19h) : < 10 km/h = congestion
  - Nuit (0h-5h, 20h-23h) : < 5 km/h = congestion
- **Résultat** : Colonne `is_congested` (booléen)

#### 5. **Aggregate by Zone** (`aggregate_data`)
- **Méthode** : Grille spatiale (grid_size = 0.001° ≈ 100 mètres)
- **Calculs** :
  - `avg_speed` : Vitesse moyenne par zone
  - `congestion_rate` : Taux de congestion (0.0 à 1.0)
- **Table** : `congestion`

#### 6. **Aggregate by Edge** (`aggregate_edge`)
- **Méthode** : Agrégation par tronçon routier (edge_u, edge_v)
- **Intervalle** : 10 minutes
- **Calcul** : `avg_speed_kmh` par tronçon
- **Table** : `edge_agg`

#### 7. **Load** (`load_data`, `load_edge_agg`)
- **Insertion** : Données dans les tables PostgreSQL
- **Gestion** : `ON CONFLICT DO UPDATE` pour éviter les doublons
- **Validation** : Vérification des colonnes et types

#### 8. **Train Model** (`train_model`)
- **Fréquence** : Exécutée à chaque cycle (peut être optimisée)
- **Algorithme** : Random Forest Regressor
- **Features** :
  - Lags de vitesse (1, 2, 3, 4, 5, 6 intervalles)
  - Heure de la journée
  - Jour de la semaine
- **Sauvegarde** : `models/rf_edge_speed.pkl`

#### 9. **Predict** (`predict`)
- **Données** : Dernière heure de `edge_agg`
- **Prédiction** : Vitesse future pour chaque tronçon
- **Table** : `predictions`

#### 10. **Send Alerts** (`send_alerts`)
- **Déclenchement** : Si `congestion_index > 0.6` (60% de réduction de vitesse)
- **Protection** : Debounce de 15 minutes par chauffeur
- **Contenu** : Localisation + Route alternative + Indice de congestion
- **Méthode** : WhatsApp via Twilio

---

## Composants principaux

### 1. Script ETL (`src/Script_ETL.py`)

**Fonctions principales** :
- `extract_recent_data()` : Extraction des données GPS
- `clean_data()` : Nettoyage des données
- `detect_congestion()` : Détection d'embouteillages
- `aggregate_by_zone()` : Agrégation spatiale
- `aggregate_by_edge()` : Agrégation par tronçon
- `load_to_db()` : Chargement dans PostgreSQL
- `load_edge_agg_to_db()` : Chargement des agrégations edge
- `load_predictions_to_db()` : Chargement des prédictions

**Gestion d'erreurs** : Try/except complet avec rollback et logs détaillés

### 2. Map Matching (`src/mapmatching.py`)

**Fonctions principales** :
- `telecharger_reseau()` : Télécharge le réseau routier OSM
- `effectuer_mapmatching()` : Associe les points GPS aux routes
- `associer_points_aux_routes()` : Jointure spatiale optimisée

**Optimisations** :
- Cache du réseau routier (évite les re-téléchargements)
- Limitation à 30 points par exécution
- Distance max de 50 mètres

### 3. Machine Learning (`src/model.py`)

**Fonctions principales** :
- `prepare_features()` : Création des features (lags, heure, jour)
- `train_model()` : Entraînement du modèle Random Forest
- `predict_next()` : Prédiction de la vitesse future

**Modèle** :
- **Algorithme** : Random Forest Regressor
- **Features** : 6 lags + heure + jour de la semaine
- **Métrique** : R² (coefficient de détermination)

### 4. Baseline (`src/baseline.py`)

**Fonction principale** :
- `compute_hourly_baseline()` : Calcule la médiane de vitesse par heure

**Utilisation** : Référence pour calculer l'indice de congestion

### 5. Système d'alertes (`src/alert.py`)

**Fonctions principales** :
- `fetch_current_congestion()` : Récupère les congestions actuelles
- `get_edge_coordinates()` : Coordonnées GPS des tronçons
- `find_alternative_route()` : Trouve une route alternative
- `create_alert_message()` : Crée le message enrichi
- `send_whatsapp()` : Envoie via Twilio
- `run_alerts()` : Fonction principale

**Paramètres** :
- `ALERT_THRESHOLD` : 0.6 (60% de réduction de vitesse)
- `DEBOUNCE_MIN` : 900 secondes (15 minutes)

---

## Base de données

### Schéma de données

#### Table `gps_points`
Stoque les points GPS bruts des véhicules.

```sql
CREATE TABLE gps_points (
    id SERIAL PRIMARY KEY,
    driver_id VARCHAR(50) NOT NULL,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    speed DECIMAL(5, 2) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Table `congestion`
Agrégation par zones géographiques (grille).

```sql
CREATE TABLE congestion (
    id SERIAL PRIMARY KEY,
    lat_bin DECIMAL(10, 8) NOT NULL,
    lon_bin DECIMAL(11, 8) NOT NULL,
    avg_speed DECIMAL(5, 2) NOT NULL,
    congestion_rate DECIMAL(3, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Table `edge_agg`
Agrégation par tronçon routier (edge).

```sql
CREATE TABLE edge_agg (
    id SERIAL PRIMARY KEY,
    edge_u BIGINT NOT NULL,
    edge_v BIGINT NOT NULL,
    ts TIMESTAMP NOT NULL,
    avg_speed_kmh DECIMAL(5, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edge_u, edge_v, ts)
);
```

#### Table `predictions`
Prédictions de vitesse future.

```sql
CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    edge_u BIGINT NOT NULL,
    edge_v BIGINT NOT NULL,
    ts TIMESTAMP NOT NULL,
    pred_speed_kmh DECIMAL(5, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edge_u, edge_v, ts)
);
```

#### Table `edge_hourly_baseline`
Baselines de vitesse par heure (référence).

```sql
CREATE TABLE edge_hourly_baseline (
    edge_u BIGINT NOT NULL,
    edge_v BIGINT NOT NULL,
    hour INTEGER NOT NULL,
    baseline_kmh DECIMAL(5, 2) NOT NULL,
    PRIMARY KEY (edge_u, edge_v, hour)
);
```

#### Table `drivers_registry`
Registre des chauffeurs et leurs positions.

```sql
CREATE TABLE drivers_registry (
    id SERIAL PRIMARY KEY,
    driver_id VARCHAR(50) NOT NULL UNIQUE,
    phone_number VARCHAR(20) NOT NULL,
    current_edge_u BIGINT,
    current_edge_v BIGINT,
    current_latitude DECIMAL(10, 8),
    current_longitude DECIMAL(11, 8),
    notifications_enabled BOOLEAN DEFAULT true,
    last_alert_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Machine Learning

### Modèle de prédiction

**Algorithme** : Random Forest Regressor

**Features** :
- **Lags** : Vitesses des 6 intervalles précédents (1, 2, 3, 4, 5, 6)
- **Heure** : Heure de la journée (0-23)
- **Jour de la semaine** : 0 (Lundi) à 6 (Dimanche)

**Entraînement** :
- **Données** : Historique de `edge_agg`
- **Split** : 80% train / 20% test
- **Métrique** : R² score

**Utilisation** :
- Prédit la vitesse future pour chaque tronçon
- Stocke les prédictions dans `predictions`
- Utilisé pour anticiper les congestions

---

## Système d'alertes

### Fonctionnement

1. **Détection** : Analyse des données de `edge_agg` et calcul de l'indice de congestion
2. **Seuil** : Si `congestion_index > 0.6` (60% de réduction de vitesse)
3. **Recherche** : Identification des chauffeurs sur le tronçon encombré
4. **Debounce** : Vérification du délai depuis la dernière alerte (15 min)
5. **Envoi** : Message WhatsApp avec localisation et route alternative

### Format du message

```
EMBOUTEILLAGE DETECTE
Indice de congestion: 75%
(Vitesse réduite de 75% par rapport à la normale)

Localisation: Coordonnées: -4.3275, 15.2982
Route alternative: Avenue de la Révolution (direction Nord)

Ralentissement sur votre trajet.
```

### Indice de congestion

**Formule** :
```
Indice = 1 - (vitesse_actuelle / vitesse_baseline)
```

**Exemples** :
- **0.0 (0%)** : Pas de congestion (vitesse normale)
- **0.6 (60%)** : Congestion modérée (20 km/h au lieu de 50 km/h)
- **1.0 (100%)** : Congestion totale (arrêt, vitesse = 0)

### Timing

- **Fréquence d'analyse** : Toutes les 10 minutes
- **Délai max d'envoi** : 10 minutes après détection
- **Protection anti-spam** : 15 minutes entre deux alertes pour le même chauffeur

### Distance de détection

- **Map matching** : 50 mètres (rayon de recherche)
- **Longueur des tronçons** : 50-500 mètres (variable selon OSM)
- **Agrégation** : Par tronçon routier (edge_u, edge_v)

---

## Utilisation

### Démarrage du système

```bash
# Démarrer les services
docker-compose up -d

# Vérifier les logs
docker-compose logs -f airflow

# Accéder à Airflow
# Local : http://localhost:8081
# Production : http://africaits.com:8081
```

### Activation du DAG

1. Ouvrir l'interface Airflow : http://localhost:8081
2. Se connecter avec les identifiants
3. Trouver le DAG `congestion_etl_modular`
4. Activer le DAG (toggle ON)
5. Le DAG s'exécutera automatiquement toutes les 10 minutes

### Dashboard Streamlit

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le dashboard
streamlit run Dashboard/Visualisation.py
```

### Test du système d'alertes

```bash
# Exécuter le script de test
python test_alert.py
```

### API Flask pour alertes

```bash
# Lancer l'API
python src/alert_api.py

# Endpoints disponibles:
# POST /run_alerts - Déclencher les alertes
# GET /health - Vérifier l'état de l'API
```

---

## Monitoring et logs

### Logs Airflow

Les logs sont stockés dans `logs/` :
- `logs/dag_id=congestion_etl_modular/` : Logs par exécution de DAG
- `logs/scheduler/` : Logs du scheduler Airflow

### Monitoring des tâches

Dans l'interface Airflow :
- **Graph View** : Visualisation du DAG
- **Tree View** : État des exécutions
- **Gantt View** : Durée des tâches
- **Logs** : Détails de chaque tâche

### Métriques importantes

- **Taux de succès** : Pourcentage de tâches réussies
- **Durée d'exécution** : Temps total du pipeline
- **Alertes envoyées** : Nombre d'alertes WhatsApp
- **Prédictions générées** : Nombre de prédictions ML

---

## Troubleshooting

### Problèmes courants

#### 1. Le DAG ne s'exécute pas

**Solutions** :
- Vérifier que le DAG est activé (toggle ON)
- Vérifier les logs Airflow : `docker-compose logs airflow`
- Vérifier la connexion à la base de données

#### 2. Erreur de connexion à PostgreSQL

**Solutions** :
- Vérifier que PostgreSQL est démarré : `docker-compose ps` (local) ou vérifier la connectivité à `africaits.com:5432` (production)
- Vérifier le port : 5432 (production) ou 5433 (local)
- Vérifier les credentials dans `docker-compose.yml` ou `docker-compose.prod.yml`
- En production, vérifier la connectivité réseau : `ping africaits.com`

#### 3. Map matching échoue

**Solutions** :
- Vérifier la connexion internet (téléchargement OSM)
- Vérifier le cache OSMnx dans `cache/`
- Réduire `max_points` dans `Dags.py`

#### 4. Alertes WhatsApp ne s'envoient pas

**Solutions** :
- Vérifier les credentials Twilio dans `src/alert.py`
- Vérifier que `drivers_registry` contient des chauffeurs
- Vérifier que `notifications_enabled = true`
- Consulter les logs dans Airflow

#### 5. Les données ne se chargent pas dans la base

**Solutions** :
- Vérifier les logs de `load_*` tasks
- Vérifier que les DataFrames ne sont pas vides
- Vérifier les colonnes requises
- Vérifier les permissions PostgreSQL

### Commandes utiles

```bash
# Redémarrer les services
docker-compose restart

# Voir les logs en temps réel
docker-compose logs -f

# Arrêter les services
docker-compose down

# Nettoyer les volumes (ATTENTION: supprime les données)
docker-compose down -v

# Accéder au shell du conteneur Airflow
docker-compose exec airflow bash

# Exécuter une tâche manuellement
docker-compose exec airflow airflow tasks test congestion_etl_modular extract_data 2024-01-01
```

---

## Notes importantes

### Performance

- **Map matching** : Limité à 30 points par exécution pour éviter les timeouts
- **Cache OSM** : Le réseau routier est mis en cache pour accélérer les requêtes
- **Agrégation** : Seules les dernières données sont traitées (30 minutes)

### Sécurité

- **ATTENTION - Credentials** : Ne pas commiter les tokens Twilio dans le code
- **ATTENTION - Base de données** : Utiliser des mots de passe forts en production
- **ATTENTION - Airflow** : Changer les identifiants par défaut

### Limitations

- **Précision GPS** : Dépend de la qualité des données d'entrée
- **Couverture OSM** : Dépend de la complétude du réseau routier OpenStreetMap
- **Fréquence** : Exécution toutes les 10 minutes (pas en temps réel strict)

---

## Contribution

Pour contribuer au projet :

1. Fork le repository
2. Créer une branche (`git checkout -b feature/AmazingFeature`)
3. Commit les changements (`git commit -m 'Add some AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

---

## Licence

Ce projet est sous licence [spécifier la licence].

---

## Contact

Pour toute question ou support :
- **Email** : alidorsabue@africaits.com
- **Auteur** : Alidor SABUE

---

## Remerciements

- **OSMnx** : Pour le réseau routier OpenStreetMap
- **Apache Airflow** : Pour l'orchestration du pipeline
- **Twilio** : Pour l'API WhatsApp
- **Streamlit** : Pour le dashboard interactif

---

**Dernière mise à jour** : Novembre 2024


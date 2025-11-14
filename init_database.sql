-- Script d'initialisation de la base de données Traffic_Tracking
-- Création de la table gps_points pour stocker les données GPS

CREATE TABLE IF NOT EXISTS gps_points (
    id SERIAL PRIMARY KEY,
    driver_id VARCHAR(50) NOT NULL,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    speed DECIMAL(5, 2) NOT NULL,
    phone_number VARCHAR(20),  -- Numéro de téléphone optionnel (pour compatibilité avec anciennes données)
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Création d'un index sur timestamp pour améliorer les performances des requêtes
CREATE INDEX IF NOT EXISTS idx_gps_points_timestamp ON gps_points(timestamp);
CREATE INDEX IF NOT EXISTS idx_gps_points_driver_id ON gps_points(driver_id);

-- Création de la table congestion pour stocker les données agrégées
CREATE TABLE IF NOT EXISTS congestion (
    id SERIAL PRIMARY KEY,
    lat_bin DECIMAL(10, 8) NOT NULL,
    lon_bin DECIMAL(11, 8) NOT NULL,
    avg_speed DECIMAL(5, 2) NOT NULL,
    congestion_rate DECIMAL(3, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lat_bin, lon_bin, created_at)
);

-- Création d'un index sur les coordonnées pour améliorer les performances
CREATE INDEX IF NOT EXISTS idx_congestion_coords ON congestion(lat_bin, lon_bin);
CREATE INDEX IF NOT EXISTS idx_congestion_created_at ON congestion(created_at);

-- Création de la table edge_agg pour stocker les données agrégées par tronçon de route
CREATE TABLE IF NOT EXISTS edge_agg (
    id SERIAL PRIMARY KEY,
    edge_u BIGINT NOT NULL,
    edge_v BIGINT NOT NULL,
    ts TIMESTAMP NOT NULL,
    avg_speed_kmh DECIMAL(5, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edge_u, edge_v, ts)
);

-- Index pour améliorer les performances des requêtes
CREATE INDEX IF NOT EXISTS idx_edge_agg_edge ON edge_agg(edge_u, edge_v);
CREATE INDEX IF NOT EXISTS idx_edge_agg_ts ON edge_agg(ts);
CREATE INDEX IF NOT EXISTS idx_edge_agg_created_at ON edge_agg(created_at);

-- Création de la table predictions pour stocker les prédictions de vitesse
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    edge_u BIGINT NOT NULL,
    edge_v BIGINT NOT NULL,
    ts TIMESTAMP NOT NULL,
    pred_speed_kmh DECIMAL(5, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edge_u, edge_v, ts)
);

-- Index pour améliorer les performances des requêtes
CREATE INDEX IF NOT EXISTS idx_predictions_edge ON predictions(edge_u, edge_v);
CREATE INDEX IF NOT EXISTS idx_predictions_ts ON predictions(ts);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at);

-- Création de la table edge_hourly_baseline pour stocker les vitesses de référence par heure
CREATE TABLE IF NOT EXISTS edge_hourly_baseline (
    edge_u BIGINT NOT NULL,
    edge_v BIGINT NOT NULL,
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    baseline_kmh DECIMAL(5, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (edge_u, edge_v, hour)
);

-- Index pour améliorer les performances des requêtes
CREATE INDEX IF NOT EXISTS idx_baseline_edge ON edge_hourly_baseline(edge_u, edge_v);
CREATE INDEX IF NOT EXISTS idx_baseline_hour ON edge_hourly_baseline(hour);

-- Création de la table drivers_registry pour enregistrer les chauffeurs et leurs positions
CREATE TABLE IF NOT EXISTS drivers_registry (
    id SERIAL PRIMARY KEY,
    driver_id VARCHAR(50) NOT NULL UNIQUE,
    phone_number VARCHAR(20) NOT NULL,
    current_edge_u BIGINT,
    current_edge_v BIGINT,
    notifications_enabled BOOLEAN DEFAULT true,
    last_alert_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index pour améliorer les performances des requêtes
CREATE INDEX IF NOT EXISTS idx_drivers_registry_driver_id ON drivers_registry(driver_id);
CREATE INDEX IF NOT EXISTS idx_drivers_registry_edge ON drivers_registry(current_edge_u, current_edge_v);
CREATE INDEX IF NOT EXISTS idx_drivers_registry_notifications ON drivers_registry(notifications_enabled, current_edge_u, current_edge_v);
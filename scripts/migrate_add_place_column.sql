-- Script de migration pour ajouter la colonne 'place' aux tables road_network_*
-- À exécuter si les tables existent déjà sans la colonne 'place'

-- Ajouter la colonne 'place' aux nœuds si elle n'existe pas
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'road_network_nodes' AND column_name = 'place'
    ) THEN
        ALTER TABLE road_network_nodes ADD COLUMN place VARCHAR(100) NOT NULL DEFAULT 'Kinshasa';
        ALTER TABLE road_network_nodes DROP CONSTRAINT IF EXISTS road_network_nodes_osmid_key;
        ALTER TABLE road_network_nodes ADD CONSTRAINT road_network_nodes_place_osmid_key UNIQUE (place, osmid);
        CREATE INDEX IF NOT EXISTS idx_road_nodes_place ON road_network_nodes(place);
        RAISE NOTICE 'Colonne place ajoutée à road_network_nodes';
    ELSE
        RAISE NOTICE 'Colonne place existe déjà dans road_network_nodes';
    END IF;
END $$;

-- Ajouter la colonne 'place' aux arêtes si elle n'existe pas
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'road_network_edges' AND column_name = 'place'
    ) THEN
        ALTER TABLE road_network_edges ADD COLUMN place VARCHAR(100) NOT NULL DEFAULT 'Kinshasa';
        ALTER TABLE road_network_edges DROP CONSTRAINT IF EXISTS road_network_edges_u_v_osmid_key;
        ALTER TABLE road_network_edges ADD CONSTRAINT road_network_edges_place_u_v_osmid_key UNIQUE (place, u, v, osmid);
        CREATE INDEX IF NOT EXISTS idx_road_edges_place ON road_network_edges(place);
        RAISE NOTICE 'Colonne place ajoutée à road_network_edges';
    ELSE
        RAISE NOTICE 'Colonne place existe déjà dans road_network_edges';
    END IF;
END $$;

-- Vérification
SELECT 
    (SELECT COUNT(*) FROM road_network_nodes) as total_nodes,
    (SELECT COUNT(*) FROM road_network_edges) as total_edges,
    (SELECT COUNT(DISTINCT place) FROM road_network_nodes) as nb_cities;


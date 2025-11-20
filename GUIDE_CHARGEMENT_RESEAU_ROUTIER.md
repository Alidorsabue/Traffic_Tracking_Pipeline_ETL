# Guide : Stockage du Réseau Routier dans PostgreSQL

Ce guide explique comment stocker le réseau routier dans PostgreSQL avec PostGIS pour accélérer le mapmatching.

## Avantages

✅ **Plus rapide** : Requêtes spatiales ultra-rapides avec PostGIS (index GIST)  
✅ **Pas de dépendance internet** : Le réseau est stocké localement  
✅ **Plus fiable** : Pas de timeout de téléchargement lors du mapmatching  
✅ **Mises à jour contrôlées** : Re-exécuter le script si besoin

## Étape 1 : Installer PostGIS sur PostgreSQL

### Sur le serveur PostgreSQL (africaits.com)

⚠️ **IMPORTANT** : Vous devez être connecté avec un compte ayant les privilèges **SUPERUSER** ou **CREATEROLE**.

#### Solution A : Donner les permissions à votre utilisateur (recommandé)

**Étape 1** : Se connecter en tant qu'administrateur PostgreSQL (postgres)

```bash
# Se connecter avec psql en tant que postgres
psql -U postgres -h africaits.com -d Traffic_Tracking
```

Ou depuis pgAdmin, connectez-vous avec un compte administrateur.

**Étape 2** : Donner les droits à votre utilisateur (remplacez `Alidorsabue` par votre nom d'utilisateur)

```sql
-- Donner le droit de créer des extensions sur la base de données
GRANT CREATE ON DATABASE Traffic_Tracking TO Alidorsabue;
```

**Étape 3** : Se connecter avec votre utilisateur et créer l'extension

```bash
# Se reconnecter avec votre utilisateur
psql -U Alidorsabue -h africaits.com -d Traffic_Tracking
```

```sql
-- Se connecter à la base de données
\c Traffic_Tracking

-- Installer l'extension PostGIS (seule celle-ci est nécessaire)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Vérifier l'installation
SELECT PostGIS_version();
```

**Note** : `postgis_topology` n'est **pas obligatoire** pour notre usage. Seule l'extension `postgis` est nécessaire.

**Fichier SQL prêt** : Un script SQL est disponible dans `scripts/grant_postgis_permissions.sql` avec toutes les commandes.

#### Solution A2 : Créer l'extension directement en tant qu'administrateur

Si vous préférez, vous pouvez créer l'extension directement sans donner les droits à votre utilisateur :

```sql
-- En tant qu'administrateur (postgres)
\c Traffic_Tracking
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT PostGIS_version();
```

L'avantage : Une fois créée, l'extension est disponible pour tous les utilisateurs de la base de données.

#### Solution B : Demander à l'administrateur

Si vous n'avez pas les droits administrateur, demandez à l'administrateur PostgreSQL de la base de données d'exécuter :

```sql
-- En tant que superutilisateur ou administrateur de la base
\c Traffic_Tracking
CREATE EXTENSION IF NOT EXISTS postgis;
```

#### Solution C : Vérifier si PostGIS est déjà installé

Même avec une erreur de permission, PostGIS peut déjà être installé :

```sql
-- Vérifier si PostGIS est disponible (ne nécessite pas de droits spéciaux)
SELECT * FROM pg_available_extensions WHERE name = 'postgis';

-- Vérifier si PostGIS est déjà activé sur cette base
SELECT extname, extversion 
FROM pg_extension 
WHERE extname = 'postgis';
```

Si PostGIS est déjà installé mais pas activé sur votre base, seul un administrateur peut l'activer.

#### Solution D : Installer PostGIS sur le serveur (si pas encore installé)

Si PostGIS n'est pas installé sur le serveur PostgreSQL, l'administrateur doit :

**Sur Ubuntu/Debian** :
```bash
sudo apt-get update
sudo apt-get install postgresql-postgis
```

**Sur CentOS/RHEL** :
```bash
sudo yum install postgis
```

**Sur Docker** :
Utiliser l'image `postgis/postgis` au lieu de `postgres` :
```yaml
image: postgis/postgis:15-3.3
```

## Étape 2 : Les tables sont déjà créées

Les tables `road_network_nodes` et `road_network_edges` sont déjà définies dans `init_database.sql`.
Elles ont été créées automatiquement lors de l'initialisation de la base de données.

**Vérification** :
```sql
-- Vérifier que les tables existent
\dt road_network_*

-- Vérifier les colonnes
\d road_network_nodes
\d road_network_edges
```

## Étape 3 : Charger le réseau routier dans PostgreSQL

### Option A : Exécution manuelle (recommandée pour la première fois)

#### Sur votre machine locale (Windows)

```bash
# Dans votre environnement Python
cd C:\Users\Helpdesk\OneDrive - AITS\Bureau\MASTER IA DATA SCIENCE DIT\RECHERCHES\Traffic_tracking_Pipiline_ETL

# Activer l'environnement virtuel
.\venv\Scripts\activate

# Installer les dépendances si nécessaire
pip install -r requirements.txt

# Exécuter le script
python scripts/load_road_network_to_db.py
```

#### Sur le serveur de production (Linux)

```bash
# Se connecter au serveur
ssh root@alidor-server

# Aller dans le répertoire du projet
cd /opt/traffic-tracking

# Installer les dépendances Python nécessaires
pip3 install -r requirements-road-network.txt

# OU installer les dépendances complètes
pip3 install osmnx geopandas shapely pandas psycopg2-binary

# Vérifier que Python peut trouver le module
python3 -c "import osmnx; print('osmnx OK')"

# Exécuter le script
python3 scripts/load_road_network_to_db.py
```

**Durée estimée** : 10-30 minutes selon la connexion internet

**Note** : Si vous avez une erreur "ModuleNotFoundError", installez les dépendances avec `pip3 install -r requirements-road-network.txt`

**Ce que fait le script** :
1. Télécharge le réseau routier de Kinshasa depuis OpenStreetMap
2. Convertit en GeoDataFrames
3. Stocke dans PostgreSQL avec PostGIS
4. Crée les index spatiaux pour des requêtes rapides

### Option B : Créer un DAG Airflow (optionnel)

Si vous voulez automatiser le chargement (ex: une fois par mois), vous pouvez créer un DAG qui appelle ce script.

## Étape 4 : Vérifier le chargement

```sql
-- Vérifier le nombre de nœuds et d'arêtes
SELECT 
    (SELECT COUNT(*) FROM road_network_nodes) as nb_nodes,
    (SELECT COUNT(*) FROM road_network_edges) as nb_edges;

-- Vérifier un exemple
SELECT osmid, x, y 
FROM road_network_nodes 
LIMIT 5;

SELECT u, v, name, highway 
FROM road_network_edges 
LIMIT 5;
```

**Résultat attendu** :
- Nœuds : Plusieurs milliers (ex: 50,000+)
- Arêtes : Plusieurs dizaines de milliers (ex: 100,000+)

## Étape 5 : Le mapmatching utilise maintenant PostgreSQL

Une fois le réseau routier chargé, le mapmatching utilisera **automatiquement** ces données :

1. **Si le réseau est dans PostgreSQL** : Chargement rapide depuis la DB (quelques secondes)
2. **Si le réseau n'est pas dans PostgreSQL** : Téléchargement depuis OSM (comme avant, plus lent)

### Vérifier dans les logs

Lors de l'exécution du DAG `mapmatching_cache_hourly`, vous devriez voir :
```
✅ Réseau routier chargé depuis PostgreSQL: XXXX nœuds, YYYY arêtes
```

Au lieu de :
```
⚠️ Chargement depuis PostgreSQL échoué, téléchargement depuis OSM...
📥 Téléchargement du réseau routier depuis OpenStreetMap...
```

## Mise à jour du réseau routier

Si vous voulez mettre à jour le réseau routier (ex: nouvelles routes ajoutées à Kinshasa) :

```bash
# Ré-exécuter le script (il nettoie les anciennes données automatiquement)
python scripts/load_road_network_to_db.py
```

**Fréquence recommandée** : Une fois par trimestre ou en cas de besoin

## Dépannage

### Erreur : "permission denied for database Traffic_Tracking"

**Cause** : Vous n'avez pas les privilèges nécessaires pour créer une extension PostgreSQL.

**Solutions** :
1. **Utiliser un compte administrateur** : Connectez-vous avec le compte `postgres` ou un autre compte superutilisateur
2. **Demander à l'administrateur** : Faites exécuter `CREATE EXTENSION IF NOT EXISTS postgis;` par l'administrateur de la base de données
3. **Vérifier les privilèges** : Un administrateur peut vous donner les droits avec :
   ```sql
   -- En tant qu'administrateur
   GRANT CREATE ON DATABASE Traffic_Tracking TO VotreUtilisateur;
   ```

**Note** : `postgis_topology` n'est pas obligatoire. Seule `postgis` est nécessaire.

### Erreur : "PostGIS n'est pas installé"

```sql
-- Vérifier si PostGIS est disponible (ne nécessite pas de droits spéciaux)
SELECT * FROM pg_available_extensions WHERE name = 'postgis';

-- Vérifier si PostGIS est déjà activé
SELECT extname, extversion 
FROM pg_extension 
WHERE extname = 'postgis';

-- Si vide, installer PostGIS sur le serveur (voir Étape 1 - Solution D)
```

### Erreur : "Les tables n'existent pas"

Exécutez le script `init_database.sql` pour créer les tables :
```sql \i init_database.sql
```

### Erreur : "Aucun nœud/arête trouvé dans PostgreSQL"

Le réseau routier n'a pas été chargé. Exécutez :
```bash
python scripts/load_road_network_to_db.py
```

### Le mapmatching télécharge toujours depuis OSM

Vérifier que :
1. PostGIS est installé
2. Les tables `road_network_nodes` et `road_network_edges` contiennent des données
3. Les logs ne montrent pas d'erreur lors du chargement depuis PostgreSQL

## Performances attendues

**Avant** (téléchargement OSM à chaque fois) :
- Téléchargement : 5-15 minutes
- Mapmatching : 1-3 minutes par 50 points
- **Total : 6-18 minutes**

**Après** (PostgreSQL + PostGIS) :
- Chargement depuis DB : 2-5 secondes
- Mapmatching : 10-30 secondes par 50 points (requêtes spatiales optimisées)
- **Total : 15-35 secondes**

**Gain de performance : ~95% plus rapide** 🚀

## Structure des données

### `road_network_nodes`
- `osmid` : Identifiant OpenStreetMap du nœud
- `geometry` : Point géographique (PostGIS)
- `x`, `y` : Coordonnées (pour compatibilité)

### `road_network_edges`
- `u`, `v` : IDs des nœuds de départ et d'arrivée
- `osmid` : Identifiant OpenStreetMap de l'arête
- `name` : Nom de la route
- `highway` : Type de route (ex: 'primary', 'secondary')
- `geometry` : Ligne géographique (PostGIS)
- `length_m` : Longueur en mètres

## Index spatiaux

Les index GIST sur les colonnes `geometry` permettent des requêtes spatiales ultra-rapides :
```sql
-- Exemple de requête spatiale optimisée
SELECT *
FROM road_network_edges
WHERE ST_DWithin(
    geometry,
    ST_MakePoint(15.2951, -4.3276),  -- Point GPS
    0.001  -- Distance en degrés (~100m)
);
```

Ces index sont créés automatiquement par `init_database.sql`.

## Support

En cas de problème :
1. Vérifier les logs du script `load_road_network_to_db.py`
2. Vérifier les logs du DAG `mapmatching_cache_hourly` dans Airflow
3. Vérifier que PostGIS est bien installé sur le serveur PostgreSQL


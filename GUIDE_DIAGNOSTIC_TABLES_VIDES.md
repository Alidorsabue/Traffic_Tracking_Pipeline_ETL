# Guide de Diagnostic : Tables Toujours Vides

## Problème
Les DAGs s'exécutent sans erreur, mais les tables suivantes restent vides :
- `edge_agg`
- `mapmatching_cache`
- `predictions`
- `edge_hourly_baseline`

## Chaîne de Dépendances

Les tables dépendent les unes des autres dans cet ordre :

```
gps_points (source: app mobile)
    ↓
mapmatching_cache (DAG: mapmatching_cache_hourly)
    ↓
edge_agg (DAG: traffic_advanced_analysis)
    ↓
predictions (DAG: traffic_advanced_analysis)
edge_hourly_baseline (DAG: compute_baseline_daily)
```

## Diagnostic Étape par Étape

### 1. Vérifier la Table Source : `gps_points`

**Question** : Est-ce que l'app mobile envoie des données à la base de données ?

**Vérification** :
```sql
SELECT COUNT(*) as total, 
       MIN(timestamp) as oldest, 
       MAX(timestamp) as newest
FROM gps_points;
```

**Si la table est vide** :
- ❌ L'app mobile n'envoie pas de données
- ❌ La connexion à la base de données ne fonctionne pas
- ❌ La table n'existe pas dans la base de données

**Solution** :
1. Vérifier que l'app mobile est configurée avec la bonne URL de base de données
2. Vérifier les logs de l'app mobile pour voir s'il y a des erreurs de connexion
3. Vérifier que la table `gps_points` existe : `\d gps_points` (dans psql)

### 2. Vérifier le Cache Mapmatching : `mapmatching_cache`

**Question** : Le DAG `mapmatching_cache_hourly` s'exécute-t-il et remplit-il le cache ?

**Vérification** :
```sql
SELECT COUNT(*) as total,
       COUNT(CASE WHEN edge_u IS NOT NULL THEN 1 END) as matched,
       MAX(processed_at) as last_update
FROM mapmatching_cache
WHERE processed_at > NOW() - INTERVAL '2 hours';
```

**Si la table est vide** :
- ❌ Le DAG `mapmatching_cache_hourly` ne s'exécute pas
- ❌ Le DAG `mapmatching_cache_hourly` échoue silencieusement
- ❌ Les données GPS ne peuvent pas être matchées à des routes

**Solution** :
1. Vérifier dans Airflow UI que le DAG `mapmatching_cache_hourly` est activé (ON/OFF)
2. Vérifier les logs du DAG pour voir s'il y a des erreurs
3. Déclencher manuellement le DAG pour voir les erreurs en temps réel
4. Vérifier que le module `src.mapmatching` fonctionne correctement

### 3. Vérifier l'Agrégation par Edge : `edge_agg`

**Question** : Le DAG `traffic_advanced_analysis` charge-t-il des données dans `edge_agg` ?

**Vérification** :
```sql
SELECT COUNT(*) as total,
       MIN(ts) as oldest,
       MAX(ts) as newest
FROM edge_agg
WHERE ts > NOW() - INTERVAL '24 hours';
```

**Si la table est vide** :
- ❌ Le cache `mapmatching_cache` est vide (voir étape 2)
- ❌ Le DAG `traffic_advanced_analysis` ne charge pas les données
- ❌ Les données matchées n'ont pas les colonnes nécessaires (`edge_u`, `edge_v`)

**Solution** :
1. Résoudre d'abord le problème de `mapmatching_cache` (étape 2)
2. Vérifier les logs du DAG `traffic_advanced_analysis` pour voir les erreurs
3. Vérifier que la fonction `load_edge_agg_to_db()` s'exécute correctement

### 4. Vérifier les Prédictions : `predictions`

**Question** : Le modèle ML génère-t-il des prédictions ?

**Vérification** :
```sql
SELECT COUNT(*) as total,
       MIN(ts) as oldest,
       MAX(ts) as newest
FROM predictions
WHERE ts > NOW() - INTERVAL '24 hours';
```

**Si la table est vide** :
- ❌ La table `edge_agg` est vide (voir étape 3)
- ❌ Le modèle ML ne peut pas s'entraîner (pas de données historiques)
- ❌ La fonction `predict_next()` échoue

**Solution** :
1. Résoudre d'abord le problème de `edge_agg` (étape 3)
2. Vérifier les logs du DAG `traffic_advanced_analysis` pour la tâche `train_model`
3. Vérifier que le modèle s'entraîne correctement avec les données disponibles

### 5. Vérifier la Baseline : `edge_hourly_baseline`

**Question** : Le DAG `compute_baseline_daily` calcule-t-il la baseline ?

**Vérification** :
```sql
SELECT COUNT(*) as total,
       COUNT(DISTINCT edge_u || '-' || edge_v) as unique_edges,
       COUNT(DISTINCT hour) as unique_hours
FROM edge_hourly_baseline;
```

**Si la table est vide** :
- ❌ La table `edge_agg` est vide (voir étape 3)
- ❌ Le DAG `compute_baseline_daily` ne s'exécute pas ou échoue
- ❌ Il n'y a pas assez de données historiques (moins de 1 jour)

**Solution** :
1. Résoudre d'abord le problème de `edge_agg` (étape 3)
2. Vérifier que le DAG `compute_baseline_daily` est activé et s'exécute
3. Vérifier les logs du DAG pour voir les erreurs

## Script de Diagnostic Automatique

Un script de diagnostic automatique a été créé : `scripts/diagnostic_tables.py`

**Utilisation** :
```bash
# Dans l'environnement Docker Airflow
cd /opt/airflow
python scripts/diagnostic_tables.py

# Ou depuis la machine locale (si Python est configuré)
python scripts/diagnostic_tables.py
```

Ce script vérifie automatiquement :
- Si chaque table existe
- Si chaque table contient des données
- Les dépendances entre les tables
- Donne des recommandations pour résoudre les problèmes

## Vérifications des Logs Airflow

Pour chaque DAG, vérifiez les logs dans l'interface Airflow :

1. **Ouvrez l'interface Airflow** : http://localhost:8080 (ou l'URL de votre serveur)
2. **Sélectionnez le DAG** dans la liste
3. **Cliquez sur l'exécution récente** (carré vert/rouge)
4. **Cliquez sur chaque tâche** pour voir les logs

**Logs importants à chercher** :
- `✅` : Succès
- `⚠️` : Avertissement (données manquantes)
- `❌` : Erreur
- `Aucune donnée trouvée` : La source de données est vide

## Solutions Courantes

### Problème 1 : `gps_points` est vide

**Cause** : L'app mobile n'envoie pas de données

**Solution** :
1. Vérifier la configuration de l'app mobile (URL de la base de données)
2. Vérifier que l'app mobile a les permissions réseau
3. Tester la connexion à la base de données depuis l'app mobile
4. Vérifier les logs de l'app mobile pour les erreurs

### Problème 2 : `mapmatching_cache` est vide

**Cause** : Le DAG `mapmatching_cache_hourly` ne s'exécute pas ou échoue

**Solution** :
1. Activer le DAG dans Airflow UI (toggle ON/OFF)
2. Déclencher manuellement le DAG pour voir les erreurs
3. Vérifier que OSMnx peut télécharger les données de route
4. Vérifier que les coordonnées GPS sont valides (latitude: -90 à 90, longitude: -180 à 180)

### Problème 3 : `edge_agg` est vide même si `mapmatching_cache` contient des données

**Cause** : Les données matchées n'ont pas les colonnes nécessaires ou sont filtrées

**Solution** :
1. Vérifier les logs du DAG `traffic_advanced_analysis` pour voir les messages
2. Vérifier que les colonnes `edge_u` et `edge_v` ne sont pas NULL dans `mapmatching_cache`
3. Vérifier que la fonction `aggregate_by_edge()` retourne des données

### Problème 4 : Toutes les tables sont vides mais les DAGs s'exécutent

**Cause** : Les fonctions retournent des DataFrames vides sans lever d'erreur

**Solution** :
1. Utiliser le script `diagnostic_tables.py` pour identifier où les données se perdent
2. Vérifier les logs de chaque tâche dans Airflow
3. Ajouter plus de logging dans les fonctions pour voir ce qui se passe

## Améliorations Apportées

Les modifications suivantes ont été apportées pour améliorer le diagnostic :

1. **Fonction `extract_recent_data()` améliorée** :
   - Vérifie si la table existe et contient des données
   - Logs détaillés sur le nombre de lignes trouvées
   - Gestion d'erreurs améliorée

2. **Fonction `extract_task()` améliorée** :
   - Logs détaillés sur le nombre de lignes extraites
   - Vérification que le DataFrame n'est pas vide
   - Messages d'erreur clairs

3. **Script de diagnostic automatique** :
   - Vérifie toutes les tables en une seule commande
   - Donne des recommandations spécifiques
   - Identifie les problèmes de dépendances

## Prochaines Étapes

1. Exécuter le script de diagnostic : `python scripts/diagnostic_tables.py`
2. Vérifier les logs de chaque DAG dans Airflow
3. Identifier la première table vide dans la chaîne
4. Résoudre le problème à la source (probablement `gps_points` ou `mapmatching_cache`)
5. Les autres tables se rempliront automatiquement une fois la source corrigée


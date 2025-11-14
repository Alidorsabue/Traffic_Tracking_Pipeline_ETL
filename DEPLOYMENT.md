# Guide de Déploiement en Production

Ce guide vous accompagne dans le déploiement du système de suivi de trafic en production.

## Prérequis

- Docker et Docker Compose installés
- Accès au serveur de production
- Variables d'environnement configurées (voir ci-dessous)

## Configuration des Variables d'Environnement

### 1. Créer le fichier `.env`

```bash
cp .env.example .env
```

### 2. Modifier le fichier `.env` avec vos valeurs réelles

**ATTENTION - IMPORTANT : Ne jamais commiter le fichier `.env` !**

```bash
# Base de données PostgreSQL (Production sur africaits.com)
POSTGRES_HOST=africaits.com
POSTGRES_PORT=5432
POSTGRES_DB=Traffic_Tracking
POSTGRES_USER=Alidorsabue
POSTGRES_PASSWORD=Virgi@1996

# Configuration Airflow
AIRFLOW_USERNAME=Alidorsabue
AIRFLOW_PASSWORD=Virgi@1996
AIRFLOW_FIRSTNAME=Alidor
AIRFLOW_LASTNAME=SABUE
AIRFLOW_EMAIL=sabuetshibangualidor@gmail.com
AIRFLOW_EXECUTOR=LocalExecutor

# Configuration Twilio (WhatsApp API)
TWILIO_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=votre_token_twilio
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Paramètres d'alerte
ALERT_THRESHOLD=0.6
DEBOUNCE_MIN=900

# Configuration de l'environnement
ENVIRONMENT=production
DEBUG=false

# Configuration du Dashboard Streamlit (optionnel)
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
```

### 3. Générer des mots de passe sécurisés

```bash
# Pour PostgreSQL
openssl rand -base64 32

# Pour Airflow
openssl rand -base64 32
```

## Déploiement avec Docker Compose

### 1. Initialiser la base de données

La base de données PostgreSQL est déjà opérationnelle sur le serveur `africaits.com`.

Pour initialiser ou mettre à jour les tables :

```bash
# Se connecter à la base de données de production
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -f init_database.sql
```

Ou manuellement :

```bash
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking
```

Puis exécuter le contenu de `init_database.sql`.

### 2. Démarrer les services

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.example up -d
```

### 3. Vérifier les logs

```bash
# Logs Airflow
docker-compose -f docker-compose.prod.yml logs -f airflow

# Logs PostgreSQL
docker-compose -f docker-compose.prod.yml logs -f postgres
```

### 4. Accéder à l'interface Airflow

- URL : http://africaits.com:8081 (ou http://alidor-server:8081)
- Utilisateur : Alidorsabue
- Mot de passe : Virgi@1996

## Sécurité en Production

### 1. Mots de passe forts

- Utilisez des mots de passe d'au moins 16 caractères
- Mélangez lettres, chiffres et caractères spéciaux
- Ne réutilisez pas les mots de passe entre services

### 2. Firewall

```bash
# Autoriser uniquement les ports nécessaires
ufw allow 5432/tcp    # PostgreSQL (si accès externe nécessaire)
ufw allow 8081/tcp    # Airflow
ufw allow 8501/tcp    # Streamlit (si utilisé)
ufw enable
```

### 3. HTTPS (recommandé)

Utilisez un reverse proxy (Nginx, Traefik) avec SSL/TLS pour exposer Airflow et Streamlit.

### 4. Sauvegardes

```bash
# Backup PostgreSQL quotidien (depuis le serveur de production)
pg_dump -h africaits.com -p 5432 -U Alidorsabue Traffic_Tracking > backup_$(date +%Y%m%d).sql
```

### 5. Monitoring

- Surveillez les logs régulièrement
- Configurez des alertes pour les erreurs critiques
- Surveillez l'espace disque

## Monitoring et Maintenance

### Commandes utiles

```bash
# Voir l'état des services
docker-compose -f docker-compose.prod.yml ps

# Redémarrer un service
docker-compose -f docker-compose.prod.yml restart airflow

# Voir les logs en temps réel
docker-compose -f docker-compose.prod.yml logs -f

# Arrêter les services
docker-compose -f docker-compose.prod.yml down

# Nettoyer (ATTENTION: supprime les volumes)
docker-compose -f docker-compose.prod.yml down -v
```

### Mise à jour

```bash
# 1. Arrêter les services
docker-compose -f docker-compose.prod.yml down

# 2. Mettre à jour le code
git pull origin main

# 3. Reconstruire les images (si nécessaire)
docker-compose -f docker-compose.prod.yml build

# 4. Redémarrer
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

## Troubleshooting

### Problème : Les services ne démarrent pas

1. Vérifier les variables d'environnement : `.env` est correctement configuré
2. Vérifier les logs : `docker-compose logs`
3. Vérifier l'espace disque : `df -h`
4. Vérifier la mémoire : `free -h`

### Problème : Erreur de connexion à PostgreSQL

1. Vérifier que PostgreSQL est accessible sur `africaits.com:5432`
2. Vérifier les credentials dans les variables d'environnement
3. Vérifier la connectivité réseau : `ping africaits.com`
4. Vérifier les logs PostgreSQL sur le serveur

### Problème : Airflow ne s'exécute pas

1. Vérifier les logs : `docker-compose logs airflow`
2. Vérifier que la base de données est accessible
3. Vérifier les variables d'environnement Airflow

## Checklist de Déploiement

- [ ] Fichier `.env` créé et configuré avec des valeurs sécurisées
- [ ] Mots de passe forts générés pour PostgreSQL et Airflow
- [ ] Base de données initialisée avec `init_database.sql`
- [ ] Services démarrés avec `docker-compose.prod.yml`
- [ ] Interface Airflow accessible
- [ ] DAG activé dans Airflow
- [ ] Logs vérifiés (pas d'erreurs critiques)
- [ ] Backup automatique configuré
- [ ] Monitoring configuré
- [ ] Firewall configuré
- [ ] HTTPS configuré (si exposition publique)

## Sauvegardes Automatiques

Créez un script de sauvegarde quotidienne :

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose -f docker-compose.prod.yml exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > $BACKUP_DIR/backup_$DATE.sql
# Garder seulement les 7 derniers backups
find $BACKUP_DIR -name "backup_*.sql" -mtime +7 -delete
```

Ajoutez à crontab :

```bash
0 2 * * * /path/to/backup.sh
```

## Support

Pour toute question ou problème :
- Email : alidorsabue@africaits.com
- Auteur : Alidor SABUE

## Guide détaillé

Pour un guide complet étape par étape, consultez **GUIDE_DEPLOIEMENT_PRODUCTION.md**

---

**Dernière mise à jour** : Novembre 2024


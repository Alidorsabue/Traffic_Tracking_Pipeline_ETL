# Guide Complet de Déploiement en Production

Ce guide vous accompagne pas à pas pour déployer le système de suivi de trafic en production sur le serveur **africaits.com** (alidor-server).

---

## 📋 Table des matières

1. [Prérequis](#prérequis)
2. [Préparation du serveur](#préparation-du-serveur)
3. [Configuration de la base de données](#configuration-de-la-base-de-données)
4. [Installation des dépendances](#installation-des-dépendances)
5. [Configuration des variables d'environnement](#configuration-des-variables-denvironnement)
6. [Déploiement avec Docker](#déploiement-avec-docker)
7. [Activation du pipeline ETL](#activation-du-pipeline-etl)
8. [Vérification et tests](#vérification-et-tests)
9. [Monitoring et maintenance](#monitoring-et-maintenance)
10. [Sécurité](#sécurité)
11. [Troubleshooting](#troubleshooting)

---

## 🔧 Prérequis

### Sur le serveur de production (africaits.com)

- **Docker** (version 20.10 ou supérieure)
- **Docker Compose** (version 2.0 ou supérieure)
- **PostgreSQL** (version 18) - Déjà installé et opérationnel
- **Git** (pour cloner/mettre à jour le code)
- **Accès SSH** au serveur
- **Ports ouverts** :
  - `5432` : PostgreSQL
  - `8081` : Airflow Web UI
  - `8501` : Streamlit Dashboard (optionnel)

### Vérification des prérequis

```bash
# Vérifier Docker
docker --version
docker-compose --version

# Vérifier PostgreSQL
psql --version

# Vérifier la connexion à PostgreSQL
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -c "SELECT version();"
```

---

## 🖥️ Préparation du serveur

### 1. Se connecter au serveur

```bash
ssh user@africaits.com
# ou
ssh user@alidor-server
```

### 2. Installer Git (si nécessaire)

```bash
# Sur Ubuntu/Debian
sudo apt update
sudo apt install git -y

# Vérifier
git --version
```

### 3. Créer le répertoire de travail

```bash
# Créer le répertoire pour le projet
mkdir -p /opt/traffic-tracking
cd /opt/traffic-tracking
```

### 4. Cloner le repository depuis GitHub

**Option A : Cloner depuis GitHub (recommandé)**

```bash
# Cloner le repository
git clone https://github.com/votre-username/Traffic_tracking_Pipiline_ETL.git .

# Ou avec SSH (si configuré)
# git clone git@github.com:votre-username/Traffic_tracking_Pipiline_ETL.git .
```

**Option B : Si vous transférez les fichiers depuis votre machine locale**

```bash
# Depuis votre machine locale
scp -r /chemin/vers/Traffic_tracking_Pipiline_ETL user@africaits.com:/opt/traffic-tracking/
```

> **Note** : Pour publier votre projet sur GitHub avant de le déployer, consultez le guide **GUIDE_GITHUB_DEPLOIEMENT.md**

---

## 🗄️ Configuration de la base de données

### 1. Vérifier que PostgreSQL est accessible

```bash
# Tester la connexion
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking
```

Si la connexion échoue, vérifiez :
- Que PostgreSQL est démarré
- Que l'utilisateur `Alidorsabue` existe
- Que le mot de passe est correct
- Que le firewall autorise les connexions

### 2. Initialiser les tables

```bash
# Depuis le répertoire du projet
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -f init_database.sql
```

**Vérification** :

```bash
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -c "\dt"
```

Vous devriez voir les tables suivantes :
- `gps_points`
- `congestion`
- `edge_agg`
- `predictions`
- `edge_hourly_baseline`
- `drivers_registry`

### 3. Vérifier les permissions

Assurez-vous que l'utilisateur `Alidorsabue` a les permissions nécessaires :

```sql
-- Se connecter en tant qu'administrateur PostgreSQL
GRANT ALL PRIVILEGES ON DATABASE Traffic_Tracking TO Alidorsabue;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO Alidorsabue;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO Alidorsabue;
```

---

## 📦 Installation des dépendances

### 1. Vérifier que Docker est installé

```bash
# Installer Docker (si nécessaire)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Installer Docker Compose (si nécessaire)
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Vérifier les permissions Docker

```bash
# Ajouter l'utilisateur au groupe docker (si nécessaire)
sudo usermod -aG docker $USER
# Déconnexion/reconnexion requise pour que les changements prennent effet
```

---

## ⚙️ Configuration des variables d'environnement

### 1. Créer le fichier `.env` depuis l'exemple

```bash
cd /opt/traffic-tracking

# Copier le fichier d'exemple
cp .env.example .env

# Éditer avec vos valeurs réelles
nano .env
```

### 2. Contenu du fichier `.env`

```bash
# Base de données PostgreSQL (Production)
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
AIRFLOW_EMAIL=alidorsabue@africaits.com
AIRFLOW_EXECUTOR=LocalExecutor
AIRFLOW_PORT=8081

# Configuration Twilio (WhatsApp API)
TWILIO_SID=votre_twilio_sid
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

### 3. Sécuriser le fichier `.env`

```bash
# Changer les permissions (lecture seule pour le propriétaire)
chmod 600 .env

# Ajouter .env au .gitignore (si vous utilisez Git)
echo ".env" >> .gitignore
```

---

## 🐳 Déploiement avec Docker

### 1. Vérifier la configuration Docker Compose

```bash
# Vérifier que docker-compose.prod.yml existe
ls -la docker-compose.prod.yml
```

### 2. Démarrer les services

```bash
# Démarrer en arrière-plan
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

### 3. Vérifier que les conteneurs sont en cours d'exécution

```bash
# Voir l'état des conteneurs
docker-compose -f docker-compose.prod.yml ps

# Vous devriez voir un conteneur "airflow" avec le statut "Up"
```

### 4. Vérifier les logs

```bash
# Logs en temps réel
docker-compose -f docker-compose.prod.yml logs -f airflow

# Logs des 100 dernières lignes
docker-compose -f docker-compose.prod.yml logs --tail=100 airflow
```

**Attendez quelques minutes** que Airflow initialise complètement. Vous devriez voir des messages comme :
- "Database ready"
- "Creating user"
- "Starting webserver"
- "Starting scheduler"

---

## 🚀 Activation du pipeline ETL

### 1. Accéder à l'interface Airflow

Ouvrez votre navigateur et allez à :
```
http://africaits.com:8081
```

ou

```
http://alidor-server:8081
```

### 2. Se connecter

- **Utilisateur** : `Alidorsabue`
- **Mot de passe** : `Virgi@1996`

### 3. Activer le DAG

1. Dans l'interface Airflow, trouvez le DAG `congestion_etl_modular`
2. Cliquez sur le **toggle** à gauche du nom du DAG pour l'activer (il doit passer de gris à vert)
3. Le DAG devrait commencer à s'exécuter automatiquement toutes les 10 minutes

### 4. Vérifier l'exécution

1. Cliquez sur le nom du DAG pour voir le graphique
2. Vérifiez que les tâches s'exécutent correctement (couleur verte = succès)
3. Cliquez sur une tâche pour voir les logs détaillés

---

## ✅ Vérification et tests

### 1. Test de connexion à la base de données

```bash
# Depuis le conteneur Airflow
docker-compose -f docker-compose.prod.yml exec airflow python -c "
import psycopg2
conn = psycopg2.connect(
    host='africaits.com',
    port=5432,
    database='Traffic_Tracking',
    user='Alidorsabue',
    password='Virgi@1996'
)
print('✅ Connexion à la base de données réussie!')
conn.close()
"
```

### 2. Test du système d'alertes

```bash
# Tester l'envoi d'une alerte (depuis le conteneur)
docker-compose -f docker-compose.prod.yml exec airflow python -c "
from src.alert import run_alerts
result = run_alerts()
print(f'Résultat: {result}')
"
```

### 3. Vérifier que les données sont collectées

```bash
# Vérifier les données GPS
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -c "
SELECT COUNT(*) as total_points, 
       MAX(timestamp) as dernier_point 
FROM gps_points;
"

# Vérifier les agrégations
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -c "
SELECT COUNT(*) as total_edges, 
       MAX(ts) as dernier_aggregation 
FROM edge_agg;
"
```

### 4. Vérifier le Dashboard Streamlit (optionnel)

```bash
# Installer Streamlit (si nécessaire)
pip install streamlit streamlit-folium

# Lancer le dashboard
streamlit run Dashboard/Visualisation.py --server.port 8501 --server.address 0.0.0.0
```

Accédez ensuite à : `http://africaits.com:8501`

---

## 📊 Monitoring et maintenance

### 1. Commandes utiles

```bash
# Voir l'état des services
docker-compose -f docker-compose.prod.yml ps

# Voir les logs en temps réel
docker-compose -f docker-compose.prod.yml logs -f airflow

# Redémarrer un service
docker-compose -f docker-compose.prod.yml restart airflow

# Arrêter les services
docker-compose -f docker-compose.prod.yml down

# Redémarrer tous les services
docker-compose -f docker-compose.prod.yml restart
```

### 2. Vérifier l'espace disque

```bash
# Vérifier l'espace disque disponible
df -h

# Vérifier l'espace utilisé par Docker
docker system df
```

### 3. Nettoyer les logs anciens

```bash
# Nettoyer les logs Airflow de plus de 7 jours
find logs/ -type f -mtime +7 -delete

# Nettoyer les images Docker non utilisées
docker system prune -a
```

### 4. Sauvegardes automatiques

Créez un script de sauvegarde quotidienne :

```bash
# Créer le script
nano /opt/traffic-tracking/backup.sh
```

Contenu du script :

```bash
#!/bin/bash
BACKUP_DIR="/opt/traffic-tracking/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Sauvegarder la base de données
pg_dump -h africaits.com -p 5432 -U Alidorsabue Traffic_Tracking > $BACKUP_DIR/backup_$DATE.sql

# Compresser la sauvegarde
gzip $BACKUP_DIR/backup_$DATE.sql

# Garder seulement les 7 derniers backups
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete

echo "Sauvegarde terminée: backup_$DATE.sql.gz"
```

Rendre le script exécutable :

```bash
chmod +x /opt/traffic-tracking/backup.sh
```

Ajouter à crontab pour exécution quotidienne à 2h du matin :

```bash
crontab -e
# Ajouter cette ligne :
0 2 * * * /opt/traffic-tracking/backup.sh >> /opt/traffic-tracking/backup.log 2>&1
```

---

## 🔒 Sécurité

### 1. Firewall

```bash
# Configurer le firewall (UFW)
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 5432/tcp    # PostgreSQL (si accès externe nécessaire)
sudo ufw allow 8081/tcp     # Airflow
sudo ufw allow 8501/tcp     # Streamlit (si utilisé)
sudo ufw enable
```

### 2. HTTPS (recommandé)

Pour exposer Airflow et Streamlit via HTTPS, utilisez un reverse proxy comme Nginx :

```nginx
# Configuration Nginx (exemple)
server {
    listen 80;
    server_name africaits.com;

    location /airflow {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /dashboard {
        proxy_pass http://localhost:8501;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. Mots de passe forts

Assurez-vous d'utiliser des mots de passe forts pour :
- PostgreSQL
- Airflow
- Comptes système

### 4. Mise à jour régulière

```bash
# Mettre à jour le système
sudo apt update && sudo apt upgrade -y

# Mettre à jour Docker
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io
```

---

## 🔧 Troubleshooting

### Problème : Les conteneurs ne démarrent pas

**Solutions** :
1. Vérifier les logs : `docker-compose -f docker-compose.prod.yml logs`
2. Vérifier l'espace disque : `df -h`
3. Vérifier la mémoire : `free -h`
4. Vérifier que les ports ne sont pas déjà utilisés : `netstat -tulpn | grep 8081`

### Problème : Erreur de connexion à PostgreSQL

**Solutions** :
1. Vérifier que PostgreSQL est accessible : `psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking`
2. Vérifier les credentials dans `.env`
3. Vérifier la connectivité réseau : `ping africaits.com`
4. Vérifier les logs PostgreSQL sur le serveur

### Problème : Airflow ne s'exécute pas

**Solutions** :
1. Vérifier les logs : `docker-compose -f docker-compose.prod.yml logs airflow`
2. Vérifier que la base de données est accessible
3. Vérifier les variables d'environnement Airflow
4. Redémarrer le conteneur : `docker-compose -f docker-compose.prod.yml restart airflow`

### Problème : Le DAG ne s'exécute pas

**Solutions** :
1. Vérifier que le DAG est activé (toggle vert)
2. Vérifier les logs du DAG dans l'interface Airflow
3. Vérifier que le scheduler Airflow est en cours d'exécution
4. Vérifier les dépendances Python dans `requirements-airflow.txt`

### Problème : Les alertes WhatsApp ne s'envoient pas

**Solutions** :
1. Vérifier les credentials Twilio dans `.env`
2. Vérifier que `drivers_registry` contient des chauffeurs avec `notifications_enabled = true`
3. Vérifier les logs de la tâche `send_alerts` dans Airflow
4. Tester manuellement : `docker-compose -f docker-compose.prod.yml exec airflow python -c "from src.alert import run_alerts; run_alerts()"`

---

## 📝 Checklist de déploiement

Avant de considérer le déploiement comme terminé, vérifiez :

- [ ] Docker et Docker Compose installés et fonctionnels
- [ ] PostgreSQL accessible sur `africaits.com:5432`
- [ ] Base de données initialisée avec toutes les tables
- [ ] Fichier `.env` créé et configuré
- [ ] Services Docker démarrés avec `docker-compose.prod.yml`
- [ ] Interface Airflow accessible sur `http://africaits.com:8081`
- [ ] Connexion à Airflow réussie
- [ ] DAG `congestion_etl_modular` activé
- [ ] DAG s'exécute automatiquement toutes les 10 minutes
- [ ] Toutes les tâches du DAG s'exécutent avec succès
- [ ] Données collectées dans `gps_points`
- [ ] Agrégations créées dans `edge_agg`
- [ ] Système d'alertes fonctionnel (testé)
- [ ] Sauvegardes automatiques configurées
- [ ] Firewall configuré
- [ ] Monitoring en place

---

## 📞 Support

Pour toute question ou problème :

- **Email** : alidorsabue@africaits.com
- **Auteur** : Alidor SABUE

## 📚 Guides complémentaires

- **GUIDE_GITHUB_DEPLOIEMENT.md** : Guide complet pour publier sur GitHub et déployer
- **DEPLOYMENT.md** : Guide de déploiement rapide
- **README.md** : Documentation complète du projet

---

## 🔄 Mise à jour du système

Pour mettre à jour le système après des modifications du code :

### Méthode 1 : Depuis GitHub (recommandé)

```bash
# 1. Se connecter au serveur
ssh user@africaits.com

# 2. Aller dans le répertoire du projet
cd /opt/traffic-tracking

# 3. Récupérer les dernières modifications depuis GitHub
git pull origin main

# 4. Arrêter les services
docker-compose -f docker-compose.prod.yml down

# 5. Reconstruire les images (si nécessaire)
docker-compose -f docker-compose.prod.yml build

# 6. Redémarrer
docker-compose -f docker-compose.prod.yml --env-file .env up -d

# 7. Vérifier les logs
docker-compose -f docker-compose.prod.yml logs -f airflow
```

### Méthode 2 : Script automatique

Créez un script pour automatiser la mise à jour :

```bash
# Créer le script
nano /opt/traffic-tracking/update.sh
```

Contenu :

```bash
#!/bin/bash
cd /opt/traffic-tracking
echo "Mise à jour du code depuis GitHub..."
git pull origin main

echo "Redémarrage des services..."
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml --env-file .env up -d

echo "Vérification des logs..."
sleep 5
docker-compose -f docker-compose.prod.yml logs --tail=50 airflow
```

Rendre exécutable :

```bash
chmod +x /opt/traffic-tracking/update.sh
```

Utilisation :

```bash
/opt/traffic-tracking/update.sh
```

> **Note** : Pour publier vos modifications sur GitHub, consultez **GUIDE_GITHUB_DEPLOIEMENT.md**

---

**Dernière mise à jour** : Novembre 2024

**Version** : 1.0


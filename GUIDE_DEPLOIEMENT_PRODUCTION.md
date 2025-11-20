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
# Option 1 : Si PostgreSQL tourne dans Docker (dans /opt/Traffic_tracking_app/backend/)
cd /opt/Traffic_tracking_app/backend/ && docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking -c "SELECT version();"

# Option 2 : Connexion directe
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
git clone git clone https://github.com/Alidorsabue/Traffic_Tracking_Pipeline_ETL.git .

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

> **Important** : La base de données PostgreSQL tourne dans le répertoire de l'application mobile backend : `/opt/Traffic_tracking_app/backend/`

### 1. Vérifier que PostgreSQL est accessible

**Option A : Si PostgreSQL tourne dans Docker (dans `/opt/Traffic_tracking_app/backend/`)**

```bash
# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Vérifier que les conteneurs Docker sont en cours d'exécution
docker-compose ps
# ou
docker ps | grep postgres

# Se connecter à PostgreSQL via le conteneur Docker
docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking
# ou si le service s'appelle différemment
docker-compose exec db psql -U Alidorsabue -d Traffic_Tracking
```

**Option B : Connexion directe depuis l'extérieur**

```bash
# Tester la connexion depuis n'importe où
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking
```

**Option C : Connexion locale sur le serveur**


```bash
# Si PostgreSQL est accessible localement
psql -h localhost -p 5432 -U Alidorsabue -d Traffic_Tracking
```

Si la connexion échoue, vérifiez :
- Que PostgreSQL est démarré (dans Docker ou comme service système)
- Que l'utilisateur `Alidorsabue` existe
- Que le mot de passe est correct
- Que le firewall autorise les connexions
- Que le port 5432 est bien exposé dans le docker-compose

### 2. Initialiser les tables

**Si PostgreSQL tourne dans Docker (dans `/opt/Traffic_tracking_app/backend/`)** :

```bash
# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Copier le fichier init_database.sql dans le conteneur ou l'exécuter depuis l'extérieur
# Option 1 : Depuis l'extérieur (si le port est exposé)
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -f /opt/traffic-tracking/init_database.sql

# Option 2 : Via Docker (copier le fichier dans le conteneur)
docker cp /opt/traffic-tracking/init_database.sql $(docker-compose ps -q postgres):/tmp/init_database.sql
docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking -f /tmp/init_database.sql
```

**Si PostgreSQL est accessible directement** :

```bash
# Depuis le répertoire du projet
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -f init_database.sql
```

**Vérification** :

```bash
# Option 1 : Via Docker (si PostgreSQL tourne dans Docker)
cd /opt/Traffic_tracking_app/backend/
docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking -c "\dt"

# Option 2 : Connexion directe
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
# IMPORTANT: Mot de passe encodé pour URL (nécessaire si le mot de passe contient des caractères spéciaux comme @)
# Le @ doit être encodé en %40 dans les URLs de connexion
POSTGRES_PASSWORD_ENCODED=Virgi%401996

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

**Option A : Via Docker (si PostgreSQL tourne dans `/opt/Traffic_tracking_app/backend/`)** :

```bash
# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Vérifier les données GPS
docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking -c "
SELECT COUNT(*) as total_points, 
       MAX(timestamp) as dernier_point 
FROM gps_points;
"

# Vérifier les agrégations
docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking -c "
SELECT COUNT(*) as total_edges, 
       MAX(ts) as dernier_aggregation 
FROM edge_agg;
"
```

**Option B : Connexion directe** :

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

**Option A : Si PostgreSQL tourne dans Docker (dans `/opt/Traffic_tracking_app/backend/`)** :

```bash
#!/bin/bash
BACKUP_DIR="/opt/traffic-tracking/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Sauvegarder la base de données via Docker
docker-compose exec -T postgres pg_dump -U Alidorsabue Traffic_Tracking > $BACKUP_DIR/backup_$DATE.sql

# Compresser la sauvegarde
gzip $BACKUP_DIR/backup_$DATE.sql

# Garder seulement les 7 derniers backups
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete

echo "Sauvegarde terminée: backup_$DATE.sql.gz"
```

**Option B : Si PostgreSQL est accessible directement** :

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

Airflow utilise HTTP par défaut, ce qui n'est **pas sécurisé** pour la production. Pour exposer Airflow via HTTPS, utilisez un reverse proxy Nginx avec un certificat SSL.

**Pourquoi HTTP par défaut ?**
- Airflow est conçu pour être utilisé en interne ou derrière un reverse proxy
- La configuration HTTPS native d'Airflow est complexe
- La solution standard est d'utiliser Nginx comme reverse proxy avec SSL/TLS

#### Méthode 1 : HTTPS avec Let's Encrypt (gratuit et recommandé)

**Étape 1 : Installer Nginx et Certbot**

```bash
# Installer Nginx
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx -y

# Vérifier que Nginx fonctionne
sudo systemctl status nginx
```

**Étape 2 : Configuration Nginx pour Airflow (HTTP temporaire)**

```bash
# Créer la configuration Nginx
sudo nano /etc/nginx/sites-available/airflow
```

Contenu du fichier :

```nginx
server {
    listen 80;
    server_name africaits.com;

    # Configuration pour Airflow
    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (nécessaire pour Airflow)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # Empêcher l'accès direct au port 8081 (sécurité)
    # Laisser le port 8081 fermé au firewall si possible
}
```

**Étape 3 : Activer la configuration**

```bash
# Créer un lien symbolique
sudo ln -s /etc/nginx/sites-available/airflow /etc/nginx/sites-enabled/

# Vérifier la configuration
sudo nginx -t

# Redémarrer Nginx
sudo systemctl restart nginx
```

**Étape 4 : Obtenir un certificat SSL avec Let's Encrypt**

```bash
# Obtenir et installer le certificat SSL
sudo certbot --nginx -d africaits.com

# Suivre les instructions interactives :
# - Entrer votre email
# - Accepter les termes
# - Choisir de rediriger HTTP vers HTTPS (recommandé)
```

Certbot modifiera automatiquement votre configuration Nginx pour utiliser HTTPS.

**Étape 5 : Configuration Nginx finale (après Certbot)**

Vérifiez que votre fichier `/etc/nginx/sites-available/airflow` contient maintenant quelque chose comme :

```nginx
server {
    listen 443 ssl;
    server_name africaits.com;

    ssl_certificate /etc/letsencrypt/live/africaits.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/africaits.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}

server {
    listen 80;
    server_name africaits.com;
    return 301 https://$server_name$request_uri;
}
```

**Étape 6 : Mettre à jour le firewall**

```bash
# Autoriser HTTPS (port 443)
sudo ufw allow 443/tcp

# Optionnel : Bloquer l'accès direct au port 8081 depuis l'extérieur
# (Airflow ne sera accessible que via Nginx sur HTTPS)
# sudo ufw delete allow 8081/tcp
```

**Étape 7 : Renouvellement automatique du certificat**

Les certificats Let's Encrypt expirent après 90 jours. Le renouvellement est automatique avec certbot :

```bash
# Tester le renouvellement
sudo certbot renew --dry-run

# Le renouvellement automatique est configuré dans /etc/cron.d/certbot
```

**Étape 8 : Mettre à jour la configuration Airflow**

Dans le fichier `.env`, vous pouvez ajouter :

```bash
# Configuration pour HTTPS via reverse proxy
AIRFLOW__WEBSERVER__BASE_URL=https://africaits.com
AIRFLOW__WEBSERVER__ENABLE_PROXY_FIX=true
```

Puis redémarrer Airflow :

```bash
docker-compose -f docker-compose.prod.yml restart airflow
```

**Accès** : Airflow sera maintenant accessible via `https://africaits.com` (au lieu de `http://africaits.com:8081`)

#### Méthode 2 : Configuration manuelle avec certificat SSL existant

Si vous avez déjà un certificat SSL :

```bash
# Créer le répertoire pour les certificats
sudo mkdir -p /etc/nginx/ssl

# Copier vos certificats (remplacer par vos chemins)
# sudo cp votre-certificat.crt /etc/nginx/ssl/africaits.com.crt
# sudo cp votre-cle.privee.key /etc/nginx/ssl/africaits.com.key

# Modifier la configuration Nginx avec les chemins de vos certificats
```

#### Sécurité supplémentaire

**Bloquer l'accès direct au port 8081 :**

```bash
# Dans le firewall, retirer l'autorisation du port 8081
sudo ufw delete allow 8081/tcp

# Airflow ne sera accessible QUE via Nginx sur HTTPS
# Depuis localhost, vous pouvez toujours accéder à http://localhost:8081 si nécessaire
```

**Ajouter une authentification HTTP basique supplémentaire (optionnel) :**

```bash
# Créer un fichier de mots de passe
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd Alidorsabue

# Ajouter dans la configuration Nginx (section location /) :
# auth_basic "Restricted Access";
# auth_basic_user_file /etc/nginx/.htpasswd;
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

### Problème : Erreur de connexion à PostgreSQL - "Connection refused"

Si vous obtenez l'erreur :
```
psql: error: connection to server at "africaits.com" (134.209.180.30), port 5432 failed: Connection refused
```

> **Important** : La base de données PostgreSQL tourne dans `/opt/Traffic_tracking_app/backend/` (application mobile backend)

**Diagnostic étape par étape** :

#### 1. Vérifier que PostgreSQL est démarré dans Docker

Si PostgreSQL tourne dans Docker (dans `/opt/Traffic_tracking_app/backend/`) :

```bash
# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Vérifier que les conteneurs sont en cours d'exécution
docker-compose ps
# ou
docker ps | grep postgres

# Si PostgreSQL n'est pas démarré, le démarrer
docker-compose up -d postgres
# ou
docker-compose up -d db
```

**Si PostgreSQL tourne comme service système** :

```bash
# Sur le serveur (africaits.com), vérifier le statut de PostgreSQL
sudo systemctl status postgresql
# ou
sudo service postgresql status

# Si PostgreSQL n'est pas démarré, le démarrer
sudo systemctl start postgresql
# ou
sudo service postgresql start

# Activer PostgreSQL au démarrage
sudo systemctl enable postgresql
```

#### 2. Tester la connexion locale d'abord

**Si PostgreSQL tourne dans Docker** :

```bash
# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Se connecter via Docker
docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking
# ou
docker-compose exec db psql -U Alidorsabue -d Traffic_Tracking

# Vérifier les variables d'environnement du conteneur
docker-compose exec postgres env | grep POSTGRES
```

**Si PostgreSQL tourne comme service système** :

```bash
# Se connecter en local sur le serveur
sudo -u postgres psql

# Ou avec l'utilisateur Alidorsabue (si configuré localement)
psql -U Alidorsabue -d Traffic_Tracking
```

#### 3. Vérifier que PostgreSQL écoute sur toutes les interfaces

**Si PostgreSQL tourne dans Docker** :

Vérifier que le port 5432 est bien exposé dans le `docker-compose.yml` :

```bash
# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Vérifier la configuration docker-compose
cat docker-compose.yml | grep -A 5 postgres
# ou
cat docker-compose.yml | grep -A 5 db

# Vérifier que le port est exposé (devrait contenir "5432:5432" ou similaire)
```

Si le port n'est pas exposé, modifier le `docker-compose.yml` :

```yaml
services:
  postgres:  # ou db
    # ... autres configurations ...
    ports:
      - "5432:5432"  # S'assurer que cette ligne existe
```

Puis redémarrer le conteneur :

```bash
docker-compose down
docker-compose up -d postgres
```

**Si PostgreSQL tourne comme service système** :

PostgreSQL doit être configuré pour accepter les connexions TCP/IP depuis l'extérieur.

**Diagnostic** : Vérifier sur quelle interface PostgreSQL écoute :

```bash
# Vérifier sur quelle interface PostgreSQL écoute
sudo ss -tulpn | grep 5432
# ou
sudo netstat -tulpn | grep 5432
```

**Si vous voyez `127.0.0.1:5432`** : PostgreSQL écoute seulement sur localhost. Il faut le configurer pour écouter sur toutes les interfaces (`0.0.0.0:5432`).

**Trouver et modifier le fichier de configuration** :

```bash
# Trouver le fichier de configuration postgresql.conf (méthode recommandée)
sudo -u postgres psql -c "SHOW config_file;"

# Ou chercher manuellement
sudo find /etc -name postgresql.conf 2>/dev/null
# Ou généralement dans :
# /etc/postgresql/14/main/postgresql.conf (pour PostgreSQL 14)
# /etc/postgresql/18/main/postgresql.conf (pour PostgreSQL 18)
# /etc/postgresql/*/main/postgresql.conf (pour toutes les versions)
# /var/lib/pgsql/data/postgresql.conf (selon la distribution)

# Trouver aussi le répertoire de données
sudo -u postgres psql -c "SHOW data_directory;"
```

**Éditer le fichier postgresql.conf** :

```bash
# Éditer le fichier (utiliser le chemin trouvé avec "SHOW config_file;" ci-dessus)
# Exemples selon la version :
sudo nano /etc/postgresql/14/main/postgresql.conf  # Pour PostgreSQL 14
sudo nano /etc/postgresql/18/main/postgresql.conf  # Pour PostgreSQL 18
# ou
sudo nano /var/lib/pgsql/data/postgresql.conf  # Pour certaines distributions
```

**Modifier la ligne suivante** :
```conf
# Chercher cette ligne (généralement commentée ou avec 'localhost')
#listen_addresses = 'localhost'
# ou
#listen_addresses = '127.0.0.1'

# La modifier pour écouter sur toutes les interfaces
listen_addresses = '*'
```

**Redémarrer PostgreSQL** :
```bash
# Trouver le nom exact du service PostgreSQL
sudo systemctl list-units | grep postgresql

# Redémarrer le service PostgreSQL (remplacer 14 par votre version)
sudo systemctl restart postgresql@14-main  # Pour PostgreSQL 14
# ou
sudo systemctl restart postgresql@18-main  # Pour PostgreSQL 18
# ou
sudo systemctl restart postgresql  # Service générique (peut ne pas fonctionner)

# Vérifier que PostgreSQL écoute maintenant sur toutes les interfaces
sudo ss -tulpn | grep 5432
# ou si ss n'est pas disponible
sudo netstat -tulpn | grep 5432

# Vous devriez maintenant voir : 0.0.0.0:5432 au lieu de 127.0.0.1:5432
```

#### 4. Configurer pg_hba.conf pour autoriser les connexions distantes

**Si PostgreSQL tourne dans Docker** :

Accéder au conteneur et modifier `pg_hba.conf` :

```bash
# Aller dans le répertoire de l'application mobile backend
cd /opt/Traffic_tracking_app/backend/

# Se connecter au conteneur PostgreSQL
docker-compose exec postgres bash
# ou
docker-compose exec db bash

# Dans le conteneur, trouver et éditer pg_hba.conf
# Généralement dans /var/lib/postgresql/data/pg_hba.conf
find /var/lib/postgresql -name pg_hba.conf
nano /var/lib/postgresql/data/pg_hba.conf
```

**Ajouter ces lignes à la fin du fichier** (avant toute ligne `# TYPE`) :
```conf
# Autoriser les connexions depuis n'importe quelle IP (à adapter selon vos besoins de sécurité)
host    Traffic_Tracking    Alidorsabue    0.0.0.0/0    md5

# Ou pour plus de sécurité, autoriser seulement depuis des IPs spécifiques :
# host    Traffic_Tracking    Alidorsabue    134.209.180.0/24    md5
```

**Redémarrer le conteneur PostgreSQL** :
```bash
# Sortir du conteneur (Ctrl+D ou exit)
docker-compose restart postgres
# ou
docker-compose restart db
```

**Si PostgreSQL tourne comme service système** :

```bash
# Trouver le fichier pg_hba.conf (méthode recommandée)
sudo -u postgres psql -c "SHOW hba_file;"

# Ou chercher manuellement
sudo find /etc -name pg_hba.conf 2>/dev/null
# Ou généralement dans :
# /etc/postgresql/14/main/pg_hba.conf (pour PostgreSQL 14)
# /etc/postgresql/18/main/pg_hba.conf (pour PostgreSQL 18)
# /etc/postgresql/*/main/pg_hba.conf (pour toutes les versions)
# /var/lib/pgsql/data/pg_hba.conf (selon la distribution)

# Éditer le fichier (utiliser le chemin trouvé avec "SHOW hba_file;" ci-dessus)
sudo nano /etc/postgresql/14/main/pg_hba.conf  # Pour PostgreSQL 14
# ou
sudo nano /etc/postgresql/18/main/pg_hba.conf  # Pour PostgreSQL 18
```

**Ajouter ces lignes à la fin du fichier** (avant toute ligne `# TYPE`) :
```conf
# Autoriser les connexions depuis n'importe quelle IP (à adapter selon vos besoins de sécurité)
host    Traffic_Tracking    Alidorsabue    0.0.0.0/0    md5

# Ou pour plus de sécurité, autoriser seulement depuis des IPs spécifiques :
# host    Traffic_Tracking    Alidorsabue    134.209.180.0/24    md5
```

**Important** : Si l'utilisateur `Alidorsabue` n'existe pas encore, vous devrez d'abord le créer (voir section 9 ci-dessous).

**Redémarrer PostgreSQL** :
```bash
# Trouver le nom exact du service PostgreSQL
sudo systemctl list-units | grep postgresql

# Redémarrer le service PostgreSQL (remplacer 14 par votre version)
sudo systemctl restart postgresql@14-main  # Pour PostgreSQL 14
# ou
sudo systemctl restart postgresql@18-main  # Pour PostgreSQL 18

# Vérifier que la configuration est correcte
sudo -u postgres psql -c "SHOW hba_file;"
```

#### 5. Vérifier le firewall

```bash
# Vérifier si le port 5432 est ouvert
sudo ufw status
# ou
sudo iptables -L -n | grep 5432

# Si UFW est actif, autoriser le port 5432
sudo ufw allow 5432/tcp
sudo ufw reload

# Pour iptables (si utilisé directement)
sudo iptables -A INPUT -p tcp --dport 5432 -j ACCEPT
sudo iptables-save
```

#### 6. Vérifier que le port 5432 est bien en écoute

```bash
# Vérifier que PostgreSQL écoute sur le port 5432
sudo netstat -tulpn | grep 5432
# ou
sudo ss -tulpn | grep 5432

# Vous devriez voir quelque chose comme :
# tcp  0  0  0.0.0.0:5432  0.0.0.0:*  LISTEN  <PID>/postgres
```

#### 7. Tester la connexion depuis l'extérieur

```bash
# Depuis votre machine locale ou depuis le serveur
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking

# Si cela fonctionne, vous devriez voir le prompt psql
```

#### 8. Vérifier les logs PostgreSQL en cas d'échec

```bash
# Consulter les logs PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-18-main.log
# ou
sudo journalctl -u postgresql -f

# Tenter une connexion et observer les erreurs dans les logs
```

#### 9. Vérifier que l'utilisateur et la base de données existent

```bash
# Se connecter en tant qu'administrateur PostgreSQL
sudo -u postgres psql

# Vérifier que l'utilisateur existe
\du

# Vérifier que la base de données existe
\l

# Si l'utilisateur n'existe pas, le créer :
CREATE USER Alidorsabue WITH PASSWORD 'Virgi@1996';

# Si la base de données n'existe pas, la créer :
CREATE DATABASE Traffic_Tracking OWNER Alidorsabue;

# Donner les permissions
GRANT ALL PRIVILEGES ON DATABASE Traffic_Tracking TO Alidorsabue;
\q
```

#### 10. Résumé des commandes de vérification rapide

**Si PostgreSQL tourne dans Docker (dans `/opt/Traffic_tracking_app/backend/`)** :

```bash
# 1. Aller dans le répertoire
cd /opt/Traffic_tracking_app/backend/

# 2. Statut des conteneurs Docker
docker-compose ps
docker ps | grep postgres

# 3. Port en écoute
sudo netstat -tulpn | grep 5432
# ou
sudo ss -tulpn | grep 5432

# 4. Test de connexion via Docker
docker-compose exec postgres psql -U Alidorsabue -d Traffic_Tracking -c "SELECT version();"

# 5. Test de connexion distante
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -c "SELECT version();"

# 6. Vérifier les variables d'environnement
docker-compose exec postgres env | grep POSTGRES

# 7. Vérifier les logs du conteneur
docker-compose logs postgres | tail -50
```

**Si PostgreSQL tourne comme service système** :

```bash
# 1. Statut PostgreSQL
sudo systemctl status postgresql

# 2. Port en écoute
sudo netstat -tulpn | grep 5432

# 3. Test de connexion locale
psql -U Alidorsabue -d Traffic_Tracking -c "SELECT version();"

# 4. Test de connexion distante
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -c "SELECT version();"

# 5. Vérifier la configuration
sudo grep listen_addresses /etc/postgresql/18/main/postgresql.conf
sudo grep -E "^host" /etc/postgresql/18/main/pg_hba.conf | tail -5
```

**Note de sécurité** : Pour la production, il est recommandé de :
- Limiter les connexions distantes à des IPs spécifiques dans `pg_hba.conf`
- Utiliser SSL/TLS pour les connexions PostgreSQL
- Changer les mots de passe par défaut
- Utiliser un firewall pour restreindre l'accès au port 5432

### Problème : Erreur Airflow - "ValueError: invalid literal for int() with base 10: 'Virgi1996localhost:5432'"

Si vous obtenez cette erreur dans les logs Airflow :
```
ValueError: invalid literal for int() with base 10: 'Virgi1996localhost:5432'
```

**Cause** : Le mot de passe PostgreSQL contient des caractères spéciaux (comme `@`) qui ne sont pas encodés dans l'URL de connexion SQLAlchemy.

**Solution** :

1. **Encoder le mot de passe pour URL** : Les caractères spéciaux doivent être encodés :
   - `@` devient `%40`
   - `#` devient `%23`
   - `%` devient `%25`
   - etc.

2. **Ajouter la variable dans `.env`** :
```bash
# Éditer le fichier .env
cd /opt/traffic-tracking
nano .env
```

Ajoutez cette ligne (remplacez `Virgi@1996` par votre mot de passe avec les caractères encodés) :
```bash
# Mot de passe encodé pour URL (nécessaire si le mot de passe contient des caractères spéciaux)
POSTGRES_PASSWORD_ENCODED=Virgi%401996
```

3. **Vérifier que `docker-compose.prod.yml` utilise la variable encodée** :
   - La ligne `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` doit utiliser `${POSTGRES_PASSWORD_ENCODED}` au lieu de `${POSTGRES_PASSWORD}`

4. **Redémarrer les conteneurs** :
```bash
cd /opt/traffic-tracking
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

5. **Vérifier les logs** :
```bash
docker-compose -f docker-compose.prod.yml logs -f airflow
```

**Note** : Le fichier `docker-compose.prod.yml` a déjà été configuré pour utiliser `POSTGRES_PASSWORD_ENCODED` par défaut avec `Virgi%401996`.

### Problème : Réinitialiser la base de données Airflow

Si vous devez réinitialiser complètement la base de données Airflow (supprimer toutes les tables et les recréer) :

**Méthode 1 : Utiliser `airflow db reset` (recommandée)** :

```bash
cd /opt/traffic-tracking

# Arrêter les conteneurs
docker-compose -f docker-compose.prod.yml down

# Réinitialiser la base de données via un conteneur temporaire
docker-compose -f docker-compose.prod.yml --env-file .env run --rm airflow bash -c "
  airflow db reset --yes &&
  airflow users create --username ${AIRFLOW_USERNAME:-Alidorsabue} --password ${AIRFLOW_PASSWORD:-Virgi@1996} --firstname ${AIRFLOW_FIRSTNAME:-Alidor} --lastname ${AIRFLOW_LASTNAME:-SABUE} --role Admin --email ${AIRFLOW_EMAIL:-sabuetshibangualidor@gmail.com}
"

# Redémarrer les services
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

**Méthode 2 : Via le conteneur en cours d'exécution** :

```bash
cd /opt/traffic-tracking

# Se connecter au conteneur
docker-compose -f docker-compose.prod.yml exec airflow bash

# Dans le conteneur :
airflow db reset --yes
airflow users create --username Alidorsabue --password Virgi@1996 --firstname Alidor --lastname SABUE --role Admin --email alidorsabue@africaits.com
exit

# Redémarrer
docker-compose -f docker-compose.prod.yml restart airflow
```

**Méthode 3 : Suppression manuelle des tables PostgreSQL** :

```bash
# Se connecter à PostgreSQL et supprimer le schéma public
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking << EOF
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO Alidorsabue;
GRANT ALL ON SCHEMA public TO public;
EOF

# Redémarrer le conteneur (il initialisera automatiquement)
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

**Attention** : La réinitialisation supprimera toutes les données Airflow (DAGs, tâches, historique d'exécution, etc.). Les DAGs seront recréés au prochain démarrage si les fichiers sont dans le dossier `dags/`.

### Problème : Airflow ne s'exécute pas

**Solutions** :
1. Vérifier les logs : `docker-compose -f docker-compose.prod.yml logs airflow`
2. Vérifier que la base de données est accessible
3. Vérifier les variables d'environnement Airflow
4. Vérifier que le mot de passe est correctement encodé (voir section ci-dessus)
5. Réinitialiser la base de données si nécessaire (voir section ci-dessus)
6. Redémarrer le conteneur : `docker-compose -f docker-compose.prod.yml restart airflow`

### Problème : Le DAG ne s'exécute pas

**Solutions** :
1. Vérifier que le DAG est activé (toggle vert)
2. Vérifier les logs du DAG dans l'interface Airflow
3. Vérifier que le scheduler Airflow est en cours d'exécution
4. Vérifier les dépendances Python dans `requirements-airflow.txt`

### Problème : Les DAGs ne sont pas reconnus ou ne se chargent pas

Si les nouveaux DAGs séparés (Baseline_DAG, Alerts_DAG) ne sont pas visibles dans l'interface Airflow :

**Vérifications** :

1. **Vérifier que les fichiers sont bien dans le conteneur** :

```bash
cd /opt/traffic-tracking

# Vérifier les fichiers DAGs dans le conteneur
docker-compose -f docker-compose.prod.yml exec airflow ls -la /opt/airflow/dags/

# Vous devriez voir :
# - Alerts_DAG.py
# - Baseline_DAG.py
# - Dags.py
```

2. **Vérifier les erreurs de parsing des DAGs** :

```bash
# Voir les logs du scheduler Airflow
docker-compose -f docker-compose.prod.yml logs airflow | grep -i "dag\|error\|import"

# Ou tester le parsing des DAGs manuellement
docker-compose -f docker-compose.prod.yml exec airflow bash -c "
  cd /opt/airflow &&
  python -m py_compile dags/Dags.py &&
  python -m py_compile dags/Baseline_DAG.py &&
  python -m py_compile dags/Alerts_DAG.py &&
  echo 'Tous les fichiers DAGs sont syntaxiquement corrects'
"
```

3. **Tester les imports Python** :

```bash
# Tester les imports dans le conteneur
docker-compose -f docker-compose.prod.yml exec airflow bash -c "
  cd /opt/airflow &&
  python -c 'import sys; sys.path.insert(0, \"/opt/airflow\"); from src.Script_ETL import extract_recent_data; print(\"Import réussi\")'
"
```

4. **Forcer le rechargement des DAGs** :

```bash
# Redémarrer le scheduler Airflow pour forcer le rechargement
docker-compose -f docker-compose.prod.yml restart airflow

# Ou dans l'interface Airflow, cliquer sur le bouton "Refresh" en haut à droite
# Ou attendre quelques minutes (le scheduler recharge les DAGs toutes les ~30 secondes)
```

5. **Vérifier les IDs des DAGs** (doivent être uniques) :

Les DAGs doivent avoir des IDs uniques :
- `congestion_zone_detection` (dans Dags.py)
- `traffic_advanced_analysis` (dans Dags.py)
- `compute_baseline_daily` (dans Baseline_DAG.py)
- `proactive_alerts` (dans Alerts_DAG.py)

```bash
# Vérifier les IDs des DAGs
docker-compose -f docker-compose.prod.yml exec airflow bash -c "
  grep -h \"^[[:space:]]*'[a-z_]*',\" /opt/airflow/dags/*.py | grep -v '#' | sort
"
```

6. **Vérifier les logs spécifiques d'un DAG** :

Dans l'interface Airflow :
- Cliquer sur un DAG
- Voir la section "Info" pour les erreurs de parsing
- Voir les logs du scheduler : Admin → Logs → scheduler

**Si les DAGs sont toujours invisibles** :

```bash
# Arrêter complètement et redémarrer
cd /opt/traffic-tracking
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml --env-file .env up -d

# Attendre 2-3 minutes puis vérifier les logs
docker-compose -f docker-compose.prod.yml logs --tail=100 airflow | grep -i dag
```

### Problème : Les tâches échouent (erreurs dans les logs)

Si les tâches sont en rouge/orange dans l'interface Airflow :

**Vérifications** :

1. **Voir les logs détaillés d'une tâche** :

Dans l'interface Airflow :
- Cliquer sur une tâche en échec (carré rouge)
- Cliquer sur "Log" pour voir l'erreur complète

2. **Erreurs communes** :

**Erreur : "ModuleNotFoundError"** :
```bash
# Installer les dépendances manquantes dans le conteneur
docker-compose -f docker-compose.prod.yml exec airflow pip install <module-manquant>
```

**Erreur : "Connection refused" pour PostgreSQL** :
- Vérifier que PostgreSQL est accessible (voir section "Erreur de connexion à PostgreSQL")
- Vérifier les variables d'environnement POSTGRES_* dans le conteneur

**Erreur : "No such file or directory"** :
- Vérifier les chemins dans le code (doivent être `/opt/airflow/...`)
- Vérifier que les fichiers existent dans le conteneur

**Erreur : "Out of Memory" (code 137)** :
- Augmenter la limite de mémoire dans docker-compose.prod.yml
- Ajouter du swap (voir section précédente)

3. **Tester manuellement une tâche** :

```bash
# Tester une fonction Python directement
docker-compose -f docker-compose.prod.yml exec airflow bash -c "
  cd /opt/airflow &&
  python -c '
import sys
sys.path.insert(0, \"/opt/airflow\")
from src.Script_ETL import extract_recent_data
df = extract_recent_data()
print(f\"Données extraites: {len(df)} lignes\")
'"
```

4. **Vérifier les permissions** :

```bash
# Vérifier que les fichiers sont accessibles
docker-compose -f docker-compose.prod.yml exec airflow ls -la /opt/airflow/dags/
docker-compose -f docker-compose.prod.yml exec airflow ls -la /opt/airflow/src/
```

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

# 7. Vérifier les contenaires encours d'exécution
docker-compose -f docker-compose.prod.yml ps

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
docker-compose -f docker-compose.prod.yml ps
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


# Guide : Publier sur GitHub et Déployer sur le Serveur

Ce guide vous explique comment publier votre projet sur GitHub puis le déployer sur le serveur de production.

---

## 📋 Table des matières

1. [Préparation du projet](#préparation-du-projet)
2. [Création du repository GitHub](#création-du-repository-github)
3. [Publication sur GitHub](#publication-sur-github)
4. [Déploiement sur le serveur](#déploiement-sur-le-serveur)
5. [Mise à jour du code](#mise-à-jour-du-code)

---

## 🔧 Préparation du projet

### 1. Vérifier le fichier .gitignore

Assurez-vous que le fichier `.gitignore` exclut les fichiers sensibles :

```bash
# Vérifier le contenu de .gitignore
cat .gitignore
```

Le fichier `.gitignore` doit contenir au minimum :

```
# Fichiers sensibles
.env
.env.local
.env.production

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# Logs
logs/
*.log

# Cache
cache/
*.cache

# Modèles ML (optionnel - peut être volumineux)
models/*.pkl
!models/.gitkeep

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Docker
.dockerignore

# Sauvegardes
backups/
*.sql
*.sql.gz
```

### 2. Créer un fichier .env.example

Créez un fichier `.env.example` avec les variables d'environnement (sans les valeurs sensibles) :

```bash
# Base de données PostgreSQL (Production)
POSTGRES_HOST=africaits.com
POSTGRES_PORT=5432
POSTGRES_DB=Traffic_Tracking
POSTGRES_USER=votre_utilisateur
POSTGRES_PASSWORD=votre_mot_de_passe

# Configuration Airflow
AIRFLOW_USERNAME=votre_utilisateur
AIRFLOW_PASSWORD=votre_mot_de_passe
AIRFLOW_FIRSTNAME=Prénom
AIRFLOW_LASTNAME=Nom
AIRFLOW_EMAIL=votre_email@example.com
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

### 3. Vérifier qu'aucun fichier sensible n'est dans le repository

```bash
# Vérifier que .env n'est pas suivi par Git
git status

# Si .env apparaît, l'ajouter à .gitignore et le retirer de Git
echo ".env" >> .gitignore
git rm --cached .env
```

---

## 🐙 Création du repository GitHub

### 1. Créer un nouveau repository sur GitHub

1. Allez sur [GitHub.com](https://github.com)
2. Cliquez sur le bouton **"+"** en haut à droite
3. Sélectionnez **"New repository"**
4. Remplissez les informations :
   - **Repository name** : `Traffic_tracking_Pipiline_ETL` (ou un autre nom)
   - **Description** : "Système de suivi et prédiction du trafic - Kinshasa"
   - **Visibility** : Choisissez **Private** (recommandé) ou **Public**
   - **Ne cochez PAS** "Initialize this repository with a README" (vous avez déjà un README)
5. Cliquez sur **"Create repository"**

### 2. Copier l'URL du repository

GitHub vous donnera une URL comme :
```
https://github.com/votre-username/Traffic_tracking_Pipiline_ETL.git
```

ou en SSH :
```
git@github.com:votre-username/Traffic_tracking_Pipiline_ETL.git
```

---

## 📤 Publication sur GitHub

### 1. Initialiser Git (si pas déjà fait)

```bash
# Depuis le répertoire du projet
cd C:\Users\Helpdesk\OneDrive - AITS\Bureau\MASTER IA DATA SCIENCE DIT\RECHERCHES\Traffic_tracking_Pipiline_ETL

# Initialiser Git (si nécessaire)
git init
```

### 2. Vérifier l'état des fichiers

```bash
# Voir les fichiers qui seront ajoutés
git status
```

### 3. Ajouter les fichiers au staging

```bash
# Ajouter tous les fichiers (sauf ceux dans .gitignore)
git add .

# Vérifier ce qui sera commité
git status
```

### 4. Faire le premier commit

```bash
git commit -m "Initial commit: Système de suivi de trafic avec Airflow et PostgreSQL"
```

### 5. Ajouter le remote GitHub

```bash
# Remplacer par votre URL GitHub
git remote add origin https://github.com/votre-username/Traffic_tracking_Pipiline_ETL.git

# Vérifier
git remote -v
```

### 6. Pousser vers GitHub

```bash
# Pousser vers la branche main
git branch -M main
git push -u origin main
```

Si c'est la première fois, GitHub vous demandera de vous authentifier :
- **Option 1** : Utiliser un Personal Access Token (recommandé)
- **Option 2** : Utiliser GitHub Desktop ou GitHub CLI

### 7. Créer un Personal Access Token (si nécessaire)

1. Allez sur GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Cliquez sur **"Generate new token"**
3. Donnez un nom (ex: "Traffic Tracking Project")
4. Sélectionnez les scopes : `repo` (tous les droits)
5. Cliquez sur **"Generate token"**
6. **Copiez le token** (il ne sera affiché qu'une seule fois)
7. Utilisez ce token comme mot de passe lors du `git push`

---

## 🚀 Déploiement sur le serveur

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

### 3. Cloner le repository

```bash
# Créer le répertoire de travail
mkdir -p /opt/traffic-tracking
cd /opt/traffic-tracking

# Cloner le repository
git clone https://github.com/votre-username/Traffic_tracking_Pipiline_ETL.git .

# Ou avec SSH (si configuré)
# git clone git@github.com:votre-username/Traffic_tracking_Pipiline_ETL.git .
```

### 4. Créer le fichier .env

```bash
# Copier le fichier d'exemple
cp .env.example .env

# Éditer avec vos valeurs réelles
nano .env
```

Remplissez avec les vraies valeurs :
- `POSTGRES_HOST=africaits.com`
- `POSTGRES_USER=Alidorsabue`
- `POSTGRES_PASSWORD=Virgi@1996`
- etc.

### 5. Initialiser la base de données

```bash
# Initialiser les tables
psql -h africaits.com -p 5432 -U Alidorsabue -d Traffic_Tracking -f init_database.sql
```

### 6. Démarrer les services

```bash
# Démarrer avec Docker Compose
docker-compose -f docker-compose.prod.yml --env-file .env up -d

# Vérifier les logs
docker-compose -f docker-compose.prod.yml logs -f airflow
```

### 7. Accéder à Airflow

Ouvrez votre navigateur :
```
http://africaits.com:8081
```

Connectez-vous avec :
- Utilisateur : `Alidorsabue`
- Mot de passe : `Virgi@1996`

Activez le DAG `congestion_etl_modular`.

---

## 🔄 Mise à jour du code

### Workflow de mise à jour

#### 1. Sur votre machine locale

```bash
# Faire vos modifications
# ...

# Ajouter les changements
git add .

# Commit
git commit -m "Description des modifications"

# Pousser vers GitHub
git push origin main
```

#### 2. Sur le serveur

```bash
# Se connecter au serveur
ssh user@africaits.com

# Aller dans le répertoire du projet
cd /opt/traffic-tracking

# Récupérer les dernières modifications
git pull origin main

# Redémarrer les services (si nécessaire)
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml --env-file .env up -d

# Vérifier les logs
docker-compose -f docker-compose.prod.yml logs -f airflow
```

### Script automatique de mise à jour (optionnel)

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

---

## 🔐 Sécurité GitHub

### 1. Repository privé vs public

- **Privé** : Seuls vous et les collaborateurs peuvent voir le code
- **Public** : Tout le monde peut voir le code (éviter si contient des secrets)

**Recommandation** : Utilisez un repository **privé** pour ce projet.

### 2. Secrets et variables d'environnement

**NE JAMAIS** commiter :
- Fichiers `.env` avec de vraies valeurs
- Mots de passe
- Tokens API (Twilio, etc.)
- Clés privées

**Toujours** :
- Utiliser `.env.example` avec des valeurs factices
- Ajouter `.env` au `.gitignore`
- Utiliser GitHub Secrets pour CI/CD (si nécessaire)

### 3. Collaborateurs

Pour ajouter des collaborateurs :
1. Allez sur le repository GitHub
2. Settings → Collaborators
3. Ajoutez les utilisateurs GitHub

---

## 📝 Checklist de publication

Avant de publier sur GitHub, vérifiez :

- [ ] `.gitignore` est configuré correctement
- [ ] `.env` n'est pas dans le repository
- [ ] `.env.example` existe avec des valeurs factices
- [ ] Aucun mot de passe ou token n'est dans le code
- [ ] Les fichiers sensibles sont exclus
- [ ] Le README.md est à jour
- [ ] Les fichiers de documentation sont inclus

---

## 🆘 Problèmes courants

### Problème : "Permission denied" lors du push

**Solution** :
1. Vérifier que vous êtes authentifié : `git config --global user.name` et `git config --global user.email`
2. Utiliser un Personal Access Token au lieu du mot de passe
3. Vérifier les permissions du repository

### Problème : "Repository not found"

**Solution** :
1. Vérifier l'URL du remote : `git remote -v`
2. Vérifier que vous avez accès au repository
3. Vérifier que le repository existe sur GitHub

### Problème : Conflits lors du pull sur le serveur

**Solution** :
```bash
# Sauvegarder les modifications locales
git stash

# Récupérer les modifications
git pull origin main

# Appliquer les modifications locales (si nécessaire)
git stash pop
```

---

## 📞 Support

Pour toute question :
- **Email** : alidorsabue@africaits.com
- **Auteur** : Alidor SABUE

---

**Dernière mise à jour** : Novembre 2024


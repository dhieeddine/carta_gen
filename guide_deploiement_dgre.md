# Guide de Déploiement — Architecture Centralisée CartaGen (DGRE)

Ce document est le guide officiel pour les administrateurs système et ingénieurs de la **Direction Générale des Ressources en Eau (DGRE)** pour installer, compiler, déployer et maintenir le serveur centralisé de **CartaGen** avec **Docker Compose** et **Docker Hub**.

---

## 🏛️ 1. Principe de l'Architecture Centralisée

1. **Serveur Unique / VM** : Un serveur central (ou une VM Linux / Kali / Ubuntu Server) héberge deux conteneurs coordonnés :
   - **`cartagen_postgres`** : Base relationnelle et spatiale PostgreSQL 15 + PostGIS 3.3.
   - **`cartagen_server`** : Serveur d'application FastAPI avec système multi-agents IA (SQL, SIG, RAG Annuaire) et environnement d'exécution sandbox.
2. **Accès Utilisateur Léger** : Aucun logiciel lourd n'est installé sur les postes des 24 gouvernorats. Les ingénieurs accèdent à CartaGen via leur navigateur : `http://<IP_SERVEUR_OU_VM>:8000`.
3. **Persistance & Auto-initialisation** :
   - Les données PostgreSQL sont stockées dans le volume persistant `pgdata`.
   - Les shapefiles officiels (limite nationale, gouvernorats, régions hydrographiques) sont injectés et initialisés automatiquement dans PostGIS au premier démarrage.

---

## 🛠️ 2. Prérequis Système

* **Système d'exploitation** : Kali Linux, Ubuntu Server 22.04 LTS, Debian 12 ou Windows Server avec WSL2.
* **Ressources minimales** :
  * RAM : 8 Go (16 Go recommandés pour l'analyse spatiale).
  * Espace Disque : 20 Go SSD disponibles (le build Docker optimisé ne fait que ~3 Go).
* **Logiciels requis** :
  * [Docker](https://docs.docker.com/engine/install/) (v24+)
  * [Docker Compose](https://docs.docker.com/compose/install/) (v2+ ou v5+)
  * Un compte [Docker Hub](https://hub.docker.com/) (pour le push et la distribution d'images).

---

## 🐳 3. Construction & Publication sur Docker Hub (Ex: VM Kali)

Si vous travaillez sur une **VM Kali Linux** (avec un dossier partagé contenant le projet), suivez cette procédure pour compiler et publier l'image sur votre compte Docker Hub.

### Étape 1 : Accéder au dossier du projet partagé
Dans le terminal de la VM Kali :
```bash
cd /chemin/vers/votre/dossier_partage/carta_gen
```

### Étape 2 : Connexion à Docker Hub
```bash
docker login
# Renseignez votre identifiant Docker Hub et votre Personal Access Token (ou mot de passe)
```

### Étape 3 : Construction de l'image Docker
> Le fichier `.dockerignore` prévient l'inclusion du dossier Windows `venv/` et des fichiers temporaires volumineux.
```bash
# Remplacer <VOTRE_USERNAME_DOCKERHUB> par votre compte Docker Hub
docker build -t <VOTRE_USERNAME_DOCKERHUB>/cartagen:latest .
```

### Étape 4 : Publication sur Docker Hub
```bash
docker push <VOTRE_USERNAME_DOCKERHUB>/cartagen:latest
```

---

## 🚀 4. Déploiement avec Docker Compose

### Option A : Déploiement direct avec l'image Docker Hub (Recommandé en production)

Sur le serveur cible (ou la VM), préparez le dossier contenant `docker-compose.yml` et le fichier `.env` :

1. Créez ou modifiez le fichier `.env` :
```env
# Nom de votre image Docker Hub
DOCKER_IMAGE=<VOTRE_USERNAME_DOCKERHUB>/cartagen:latest

# Configuration Base de données PostgreSQL / PostGIS
DB_USER=postgres
DB_PASSWORD=VotreMotDePasseSecurise2026!
DB_NAME=dgre_db

# Choix du provider LLM par défaut (groq, openrouter, openai, colab)
LLM_PROVIDER=groq

# Clés API LLM Cloud
GROQ_API_KEY=gsk_votre_cle_groq_ici
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=sk-or-v1-votre_cle_openrouter_ici
OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct:free
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Tunnel Colab / Ollama (optionnel)
OLLAMA_COLAB_URL=https://votre-tunnel.ngrok-free.dev

# Sécurité & Réseau
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
LOG_LEVEL=INFO
```

2. Téléchargez l'image et démarrez les services :
```bash
docker compose pull
docker compose up -d
```

---

### Option B : Déploiement avec Build Local
Si vous préférez compiler et exécuter directement le code source local sur la même machine :
```bash
docker compose up -d --build
```

---

## 🔍 5. Vérification & Santé du Système

### 1. Contrôler l'état des conteneurs
```bash
docker compose ps
```
Vous devez observer les deux conteneurs avec le statut `Up` et `healthy` :
* `cartagen_postgres` : `healthy` (test `pg_isready`)
* `cartagen_server` : `healthy` (test HTTP `/health`)

### 2. Consulter les logs en temps réel
```bash
# Logs de l'application CartaGen
docker compose logs -f cartagen_app

# Logs de la base PostGIS
docker compose logs -f postgres_db
```

### 3. Tester l'accès HTTP
Ouvrez votre navigateur web sur :
```
http://<IP_SERVEUR_OU_VM_KALI>:8000
```
Le Dashboard d'accueil de **CartaGen** s'affiche immédiatement.

---

## 📥 6. Ingestion des Données & Gestion Quotidienne

### Ingestion des bases régionales Access (.mdb / .accdb)
1. Ouvrez l'interface web : `http://<IP_SERVEUR>:8000`.
2. Allez dans l'onglet **"Importation MDB"**.
3. Sélectionnez le **Gouvernorat** (ex: *Béja*, *Jendouba*, *Kairouan*).
4. Déposez votre fichier `.mdb` ou `.accdb`.
5. Cliquez sur **"Démarrer l'Ingestion"**.
   > *Note technique* : Le serveur sous Linux traite automatiquement le fichier grâce à la couche native `mdbtools` intégrée dans le conteneur.

### Sauvegarde automatique de la base PostGIS
Pour automatiser une sauvegarde quotidienne à 02h00 du matin, ajoutez cette ligne dans la table cron du serveur (`crontab -e`) :
```bash
0 2 * * * docker exec cartagen_postgres pg_dump -U postgres dgre_db > /opt/backups/dgre_db_$(date +\%Y\%m\%d).sql
```

### Arrêter ou redémarrer le service
```bash
# Arrêter sans perdre les données
docker compose down

# Redémarrer
docker compose restart

# Mettre à jour avec une nouvelle image Docker Hub
docker compose pull cartagen_app
docker compose up -d
```

---

## 🛡️ 7. Résolution des Problèmes Fréquents (Troubleshooting)

| Problème rencontré | Cause possible | Solution |
| :--- | :--- | :--- |
| **Impossible d'accéder au port 8000 depuis l'hôte** | Le pare-feu de la VM Kali bloque le port ou le réseau est en NAT | Dans les paramètres de la VM, passez en mode **Accès par pont (Bridged)** ou configurez une règle de redirection de port (Host 8000 -> Guest 8000). Vérifiez `ufw allow 8000`. |
| **`pg_isready` échoue ou `connection refused`** | Le conteneur postgres n'est pas encore prêt | Attendre 15 secondes. `cartagen_app` attend automatiquement que PostgreSQL soit `healthy` avant de se lancer. |
| **Erreur d'authentification Docker Hub** | Token ou mot de passe erroné | Générer un *Personal Access Token (PAT)* sur [hub.docker.com/settings/security](https://hub.docker.com/settings/security) avec les droits `Read, Write, List` et l'utiliser comme mot de passe lors de `docker login`. |
| **Shapefiles non trouvés** | Répertoire `data/raw` non monté ou manquant | Les couches spatiales de base sont déjà intégrées dans `/app/data/raw` de l'image Docker et initialisées automatiquement dans PostGIS. |

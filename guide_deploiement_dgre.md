# Guide de Déploiement - Architecture Centralisée CartaGen (DGRE)

Ce document est le guide officiel pour les administrateurs système et ingénieurs de la **Direction Générale des Ressources en Eau (DGRE)** pour installer, exécuter et maintenir le serveur unique centralisé de **CartaGen**.

---

## 🏛️ 1. Principe de l'Architecture Centralisée

1. **Serveur Unique** : Un seul serveur central (hébergé à Tunis ou sur le réseau Intranet DGRE) fait tourner la base de données **PostgreSQL / PostGIS** et le serveur Web **CartaGen**.
2. **Accès Utilisateur** : Aucun logiciel lourd à installer sur les postes de travail des 24 gouvernorats. Les ingénieurs se connectent via leur navigateur web (`http://IP_SERVEUR_DGRE:8000`).
3. **Ingestion Régionale Centralisée** : Les ingénieurs régionaux envoient leurs bases annuelles **MS Access (`.mdb` / `.accdb`)** via l'onglet **"Importation MDB"** de l'interface web.

---

## 🛠️ 2. Prérequis Système sur le Serveur

* **OS recommandé** : Ubuntu Server 22.04 LTS (ou Windows Server 2022).
* **RAM minimale** : 8 Go (16 Go recommandés).
* **Espace Disque** : 50 Go SSD.
* **Logiciels prérequis** :
  * [Docker](https://docs.docker.com/engine/install/) & [Docker Compose](https://docs.docker.com/compose/install/)

---

## 🚀 3. Procédure de Déploiement Rapide (Docker)

### Étape 1 : Cloner ou copier le projet sur le serveur
```bash
git clone https://github.com/dgre-tunisie/carta_gen.git /opt/carta_gen
cd /opt/carta_gen
```

### Étape 2 : Configurer les clés et variables d'environnement (`.env`)
Créez le fichier `.env` sur le serveur :
```env
# Configuration Base de données
DB_USER=postgres
DB_PASSWORD=MotDePasseSecuriseDGRE2026!
DB_NAME=dgre_db

# Clés API LLM (Groq / OpenRouter / OpenAI)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_votre_cle_groq_ici
OPENROUTER_API_KEY=sk-or-v1-votre_cle_openrouter_ici

```

### Étape 3 : Démarrer le serveur centralisé
```bash
docker-compose up -d --build
```

### Étape 4 : Vérification du fonctionnement
Ouvrez votre navigateur sur n'importe quel ordinateur connecté au réseau DGRE :
`http://<IP_SERVEUR_DGRE>:8000`

---

## 📥 4. Guide d'Utilisation pour l'Ingestion des Données Régionales

1. Connectez-vous sur l'interface web `http://<IP_SERVEUR_DGRE>:8000`.
2. Cliquez sur l'onglet **"Importation MDB"** en haut de la page.
3. Sélectionnez le **Gouvernorat** correspondant à vos données (ex: *Béja*, *Sfax*, *Jendouba*).
4. Parcourez et choisissez le fichier `.mdb` ou `.accdb` annuel de votre région.
5. Cliquez sur **"Démarrer l'Ingestion"**.
6. Le serveur procède à l'extraction, la vérification et l'insertion automatique des stations et des pluies dans la base PostgreSQL centrale.

---

## 🔄 5. Sauvegarde Automatique de la Base de Données

Pour configurer une sauvegarde automatique quotidienne de la base centrale PostgreSQL :
```bash
# Ajouter à la crontab du serveur (crontab -e)
0 2 * * * docker exec cartagen_postgres pg_dump -U postgres dgre_db > /opt/backups/dgre_db_$(date +\%Y\%m\%d).sql
```

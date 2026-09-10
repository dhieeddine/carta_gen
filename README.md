# CartaGen - DGRE (Direction Générale des Ressources en Eau)

CartaGen est une plateforme multi-agents d'analyse hydrologique et de cartographie automatisée conçue pour la Direction Générale des Ressources en Eau (**DGRE**) du Ministère de l'Agriculture, des Ressources Hydrauliques et de la Pêche de Tunisie.

Elle permet d'interroger en langage naturel, d'analyser, de cartographier par interpolation spatiale et d'éditer automatiquement les annuaires pluviométriques officiels de la République Tunisienne.

---

## 🏛️ Architecture du Système

L'application repose sur les principes de la **Clean Architecture (Hexagonale)** avec un système multi-agents collaboratif orchestré selon le modèle **Supervisor Pattern**, couplé à un RAG sémantique in-process et une sandbox d'exécution sécurisée.

```mermaid
graph TD
    A[Utilisateur : Interface Web / API REST / CLI] --> B[FastAPI / CORS Sécurisé]
    B --> C[Orchestrateur Multi-Agents]
    
    subgraph RAG & Contexte Sémantique
        C --> D[Zvec Vector Manager]
        D -->|Similarité Cosinus + Score Cutoff| E[Métadonnées Stations & Schémas]
    end

    subgraph Agent SQL
        C --> F[SQLGeneratorAgent]
        F -->|Sanitisation SQL & Whitelist| G[Parseur Déterministe / ProviderManager]
        G -->|PostgreSQL / PostGIS Paramétré| H[(Base de Données unifiée : dgre_db)]
    end

    subgraph Agent SIG & Templates
        C --> I[SIGGeneratorAgent]
        I -->|ProviderManager LLM| J[Génération du Code]
        J --> K[Skeleton Loader LRU Cache]
        K -->|Templates .py.template| L[Squelettes Spécialisés : IDW, Thiessen, Anomalies, etc.]
    end

    subgraph Sandbox Sécurisée
        L --> M[CodeSecurityValidator : Analyse AST]
        M -->|Code Validé| N[Exécution Isolée en Sous-processus]
        M -->|Code Rejeté : Import/Appel Suspect| O[Blocage Immédiat]
        N -->|Erreur d'Exécution| P[Boucle d'Auto-Correction LLM]
        P --> I
    end

    subgraph Sorties & Publication
        N -->|Succès| Q[Cartes Isohyètes PNG 300 DPI]
        N -->|Succès| R[Tableaux Statistiques HTML/DataFrames]
        N -->|Succès| S[Annuaires Officiels PDF DGRE]
    end
```

---

## 📁 Organisation du Code Source

```
carta_gen/
├── cartagen/
│   ├── domain/                               # Couche Métier / Domaine
│   │   ├── __init__.py
│   │   └── models/
│   │       ├── __init__.py
│   │       └── map_request.py                # Modèles de données (MapRequest, ExecutionResult, etc.)
│   │
│   └── infrastructure/                       # Couche Infrastructure
│       ├── __init__.py
│       ├── config.py                         # Configuration centralisée Pydantic BaseSettings
│       ├── agents/                           # Agents Spécialisés
│       │   ├── __init__.py
│       │   ├── orchestrator.py               # Orchestrateur central multi-agents
│       │   ├── sql_generator_agent.py        # Agent Text-to-SQL sécurisé
│       │   ├── sig_generator_agent.py        # Agent de génération de code SIG & cartographie
│       │   ├── annuaire_rag_agent.py         # Agent de génération des annuaires officiels
│       │   └── skeletons/                    # Squelettes de code géospatial modulaires
│       │       ├── __init__.py
│       │       ├── skeleton_loader.py        # Chargeur centralisé avec cache LRU
│       │       ├── mono.py.template          # Carte isohyète standard (IDW national)
│       │       ├── analysis.py.template      # Carte avec tableau d'analyse statistique
│       │       ├── single_gouv.py.template   # Zoom et découpage par gouvernorat
│       │       ├── compare_gouv.py.template  # Comparaison spatiale multi-gouvernorats
│       │       ├── region_hydro.py.template  # Découpage par région hydrographique
│       │       ├── difference.py.template    # Carte différentielle (Année N - Année N-1)
│       │       ├── anomalie.py.template      # Rapport aux normales climatiques (%)
│       │       ├── stations_density.py.template # Densité et maillage des stations
│       │       └── region_naturelle.py.template # Synthèse des 6 régions naturelles
│       │
│       ├── api/                              # Exposition HTTP (FastAPI)
│       │   ├── __init__.py
│       │   ├── app.py                        # Routes API REST, WebSocket, middleware CORS
│       │   └── static/                       # Interface Frontend Web (HTML5/CSS3/Vanilla JS)
│       │
│       ├── database/                         # Persistance et Accès Données
│       │   ├── __init__.py
│       │   ├── postgres_connection.py        # Pool de connexions PostgreSQL/PostGIS sécurisé
│       │   ├── annuaire_indexer.py           # Indexeur vectoriel des annuaires
│       │   └── vector_manager.py             # Moteur vectoriel Zvec in-process
│       │
│       ├── logging/                          # Observabilité et Logging
│       │   ├── __init__.py
│       │   └── logger.py                     # Logger structuré avec rotation de fichiers (RotatingFileHandler)
│       │
│       ├── providers/                        # Fournisseurs d'IA (LLM)
│       │   ├── __init__.py
│       │   └── provider_manager.py           # Gestionnaire unifié (Groq, OpenAI, OpenRouter, Ollama, Colab, Local)
│       │
│       └── sandbox/                          # Environnement d'Exécution Isolé
│           ├── __init__.py
│           └── sandbox_manager.py            # Sandbox avec CodeSecurityValidator (AST)
│
├── tests/                                    # Suite de Tests Automatisés
│   ├── __init__.py
│   ├── test_sql_sanitizer.py                 # Tests de sanitisation et protection SQL injection
│   ├── test_security_validator.py            # Tests de l'analyse statique AST du Sandbox
│   ├── test_skeleton_loader.py               # Tests de chargement et conformité des squelettes
│   └── test_config.py                        # Tests de validation de la configuration Pydantic
│
├── run_app.py                                # Script de démarrage de l'application Web
├── generer_annuaire_database.py              # Générateur CLI d'annuaires officiels DGRE (PDF)
├── requirements.txt                          # Dépendances Python
└── .env.example                              # Modèle de configuration des variables d'environnement
```

---

## 🔒 Sécurité & Robustesse

L'application intègre des mécanismes de défense en profondeur à chaque étape du pipeline :

1. **Validation Statique du Code (Analyse AST)** :
   * Avant toute exécution dans la Sandbox, le code Python généré par le LLM est inspecté par `CodeSecurityValidator`.
   * **Modules bloqués** : `subprocess`, `socket`, `shutil`, `http`, `urllib`, `ctypes`, etc.
   * **Fonctions et appels bloqués** : `eval`, `exec`, `__import__`, `globals`, `locals`, `os.system`, `os.popen`, `os.remove`, etc.
2. **Protection contre l'Injection SQL** :
   * Nettoyage strict via `_sanitize_sql_string` (suppression des marqueurs `--`, échappement standard des guillemets `''`).
   * Liste blanche pour les entités spatiales (`GOUVERNORATS_MAP`).
   * Requêtes d'introspection de schémas paramétrées (`%s`).
3. **Contrôle des Origines (CORS)** :
   * Origines restreintes et configurables via `ALLOWED_ORIGINS` dans `.env` (par défaut `http://localhost:8000`).
   * Restriction stricte aux méthodes nécessaires (`GET`, `POST`).
4. **Isolation de la Sandbox** :
   * Répertoire d'exécution temporaire dédié par requête.
   * Nettoyage automatique des fichiers résiduels après exécution.

---

## ⚙️ Modulaire & Haute Performance

- **Squelettes de Code Modulaires (`skeletons/`)** : Les modèles de génération SIG sont extraits dans des fichiers `.py.template` indépendants, chargés à la demande et conservés en mémoire via un cache LRU (`@lru_cache`).
- **Fournisseur LLM Unifié (`ProviderManager`)** : Prise en charge native et transparente de multiples fournisseurs :
  - **Cloud ultra-rapide** : Groq (`llama-3.3-70b-versatile`), OpenRouter (`meta-llama/llama-3.1-8b-instruct`), OpenAI (`gpt-4o-mini`).
  - **Modèles Fine-Tunés / Locaux** : Google Colab (vLLM/FastAPI), Ollama local (`CartaGen_LoRA_SQL_SIG`), GPU Kaggle ou exécution PyTorch locale 4-bit (`VisCoder2-7B`).
- **Logging Structuré** : Rotation automatique des logs (`cartagen.log`, max 5 Mo, 3 backups) et double sortie console standardisée.
- **Configuration Typée** : Validation Pydantic `BaseSettings` au démarrage pour interdire les configurations invalides.

---

## 🛠️ Fonctionnalités Métier (DGRE)

### 1. Cartographie Spatiale & Isohyètes
* **Interpolation IDW (Inverse Distance Weighting)** vectorisée sur grille fine.
* Découpage et masquage spatial précis sur les polygones nationaux et gouvernoraux en **UTM 32N (EPSG:32632)**.
* Échelles de couleurs officielles de la DGRE adaptées à chaque pas de temps (journalier, mensuel, saisonnier, annuel).
* Cartes d'anomalies pluviométriques par rapport aux normales climatiques interannuelles.

### 2. Analyse Hydrologique & Synthèses Statistiques
* Calcul des hauteurs de précipitations régionales par la méthode d'intégration spatiale des **Polygones de Thiessen (Voronoi)** pondérés par surface d'influence.
* Calcul de la lame d'eau nationale (TUNISIE) pondérée par la superficie des 6 régions naturelles :
  $$\text{Nord Ouest}, \quad \text{Nord Est}, \quad \text{Centre Ouest}, \quad \text{Centre Est}, \quad \text{Sud Ouest}, \quad \text{Sud Est}$$
* Calculs d'écarts absolus (mm) et relatifs (%), et des rapports à la normale climatiques (%).

### 3. Édition des Annuaires Pluviométriques Officiels (LaTeX / PDF)
* Génération automatisée de l'annuaire national ou régional complet conforme aux normes de publication de la DGRE :
  - Page de garde officielle avec armoiries et mentions légales.
  - Avant-propos institutionnel et description du réseau d'observation (148 stations).
  - Tableau 1 (synthèse régionale) et Tableau 2 (historique sur 8 ans avec détection des lacunes).
  - Cartographie couleur intégrée et fiches mensuelles détaillées par station.

---

## 🚀 Installation & Démarrage

### 1. Cloner le dépôt et configurer l'environnement
```bash
git clone https://github.com/dhieeddine/carta_gen.git
cd carta_gen

# Créer un environnement virtuel
python -m venv venv
venv\Scripts\activate   # Sous Windows
# source venv/bin/activate # Sous Linux/macOS

# Installer les dépendances
pip install -r requirements.txt
```

### 2. Configuration du fichier `.env`
Copiez le modèle et renseignez vos paramètres de base de données et clés API :
```bash
cp .env.example .env
```

Variables clés du fichier `.env` :
```ini
# Base de données PostgreSQL / PostGIS
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/dgre_db

# Fournisseur LLM actif (openrouter, groq, openai, ollama, colab)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=votre_cle_ici
GROQ_API_KEY=votre_cle_ici
OPENAI_API_KEY=votre_cle_ici

# Sécurité & Serveur
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
LOG_LEVEL=INFO
```

### 3. Exécuter les tests unitaires
L'application dispose d'une suite de tests automatisés couvrant les couches critiques :
```bash
python -m unittest discover -s tests -v
```

### 4. Lancer le serveur Web
```bash
python run_app.py
```
L'interface de bord est accessible sur **`http://localhost:8000/`**.

### 5. Générer un annuaire officiel en ligne de commande
```bash
# Annuaire national pour l'année 2018-2019
python generer_annuaire_database.py --year 2018 --gouv all --output Annuaire_National_2018_2019.pdf

# Annuaire régional (ex: Gouvernorat de Béja)
python generer_annuaire_database.py --year 2021 --gouv Beja --output Annuaire_Beja_2021_2022.pdf
```

---

## 🚦 État de Maturité & Éligibilité au Déploiement en Production

### 1. Déploiement en Intranet / Réseau Institutionnel DGRE : ✅ **PRÊT POUR LA PRODUCTION**
L'application est **entièrement opérationnelle et sécurisée** pour un déploiement au sein de l'infrastructure interne du Ministère, sur un réseau privé virtuel (VPN) ou sur un serveur intranet :
- **Architecture saine & modulaire** : Clean Architecture hexagonale avec séparation stricte des couches.
- **Défense en profondeur éprouvée** : Protection contre les injections SQL, isolation des scripts par analyse statique AST (`CodeSecurityValidator`), et protection contre le Path Traversal.
- **Stabilité et tests** : 24 tests automatisés unitaires et d'intégration validés à 100%.
- **Conteneurisation Docker** : Images allégées et orchestration multi-conteneurs `docker-compose` avec healthcheck.

---

### 2. Exposition en Accès Public Ouvert (Internet sans restriction) : ⚠️ **PRÉREQUIS COMPLÉMENTAIRES**

Avant d'ouvrir l'application directement au grand public sur l'Internet ouvert (sans mot de passe), une analyse des risques a identifié les exigences suivantes pour garantir la résilience et la sécurité :

> [!WARNING]
> **Points de vigilance pour une ouverture publique sur Internet :**
> 1. **Protection des routes d'administration** : Les endpoints sensibles (`/api/v1/providers/add`, `/api/v1/data/ingest-mdb`, `/api/v1/data/ingest-shapefiles`) ne doivent pas être accessibles sans authentification.
> 2. **Protection contre le DoS financier (Rate Limiting)** : Les appels aux LLM Cloud (Groq, OpenRouter, OpenAI) doivent être limités par quota IP pour éviter l'épuisement de la facturation ou la saturation CPU par des bots.
> 3. **Isolation réseau de la base de données** : Le port PostgreSQL 5432 ne doit pas être exposé sur `0.0.0.0`, mais confiné au réseau Docker interne.
> 4. **Chiffrement de bout en bout (HTTPS)** : Un reverse proxy (Nginx / Caddy / Cloudflare) avec certificat SSL valide est obligatoire en façade publique.

---

## 🗺️ Feuille de Route & Améliorations Futures (Roadmap)

Le tableau ci-dessous détaille les chantiers d'amélioration planifiés pour le passage à une échelle publique nationale :

| Axe d'Amélioration | Description | Priorité |
| :--- | :--- | :---: |
| **Authentification & Rôles (RBAC)** | Mise en place de jetons JWT / OAuth2 différenciant les ingénieurs DGRE (accès complet, upload MDB, paramétrage LLM) du grand public (consultation de cartes uniquement). | 🔴 **Haute** |
| **Limitation de Débit (Rate Limiting)** | Intégration de `slowapi` ou d'un middleware Redis limitant les requêtes anonymes à 5 générations de cartes et 10 questions chat par minute et par IP. | 🔴 **Haute** |
| **Reverse Proxy Nginx & SSL** | Configuration d'un conteneur Nginx en frontal assurant la terminaison HTTPS Let's Encrypt, la compression gzip et la protection contre les requêtes malveillantes. | 🔴 **Haute** |
| **File de Tâches Asynchrones (Celery/RQ)** | Découplage des traitements lourds (compilation d'annuaires PDF de 80 pages, interpolations IDW massives) via une file Redis/Celery avec suivi de progression en temps réel. | 🟠 **Moyenne** |
| **Mise en Cache Redis des Résultats** | Mise en cache des requêtes SQL récurrentes et des cartes d'isohyètes déjà calculées pour des temps de réponse instantanés (< 100 ms). | 🟠 **Moyenne** |
| **Monitoring & Observabilité** | Intégration de métriques Prometheus et de tableaux de bord Grafana pour surveiller la latence des agents LLM et les ressources système. | 🔵 **Basse** |


# 📘 Catalogue Détaillé des Fonctionnalités de CartaGen
## Document de Référence pour la Rédaction du Rapport de Stage (DGRE)

> **Projet** : CartaGen — Plateforme Multi-Agents d'Analyse Hydrologique, d'Interpolation Spatiale et d'Édition d'Annuaires Pluviométriques  
> **Organisme d'Accueil** : Direction Générale des Ressources en Eau (DGRE), Ministère de l'Agriculture, des Ressources Hydrauliques et de la Pêche — République Tunisienne  
> **Auteur** : Stagiaire Ingénieur  
> **Année Académique** : 2025 - 2026  

---

## 📑 Table des Matières

1. [Introduction & Contexte du Stage](#1-introduction--contexte-du-stage)
2. [Vue d'Ensemble de l'Architecture](#2-vue-densemble-de-larchitecture)
3. [Module 1 : Système Multi-Agents Collaboratif (Supervisor Pattern)](#3-module-1--système-multi-agents-collaboratif-supervisor-pattern)
4. [Module 2 : RAG Sémantique & Moteur Vectoriel In-Process (Zvec)](#4-module-2--rag-sémantique--moteur-vectoriel-in-process-zvec)
5. [Module 3 : Cartographie Géospatiale & Algorithmes Hydrologiques](#5-module-3--cartographie-géospatiale--algorithmes-hydrologiques)
6. [Module 4 : Architecture des Squelettes Modulaires (Skeletons System)](#6-module-4--architecture-des-squelettes-modulaires-skeletons-system)
7. [Module 5 : Édition Automatisée des Annuaires Pluviométriques Officiels](#7-module-5--édition-automatisée-des-annuaires-pluviométriques-officiels)
8. [Module 6 : Sécurité & Environnement d'Exécution Isolé (Sandbox Manager)](#8-module-6--sécurité--environnement-dexécution-isolé-sandbox-manager)
9. [Module 7 : Gestionnaire Unifié de Modèles d'Intelligence Artificielle](#9-module-7--gestionnaire-unifié-de-modèles-dintelligence-artificielle)
10. [Module 8 : Ingestion des Données & Pipeline de Fine-Tuning LoRA](#10-module-8--ingestion-des-données--pipeline-de-fine-tuning-lora)
11. [Module 9 : API REST Asynchrone & Interface Frontend Interactive](#11-module-9--api-rest-asynchrone--interface-frontend-interactive)
12. [Module 10 : Observabilité, Qualité de Code & Déploiement Conteneurisé](#12-module-10--observabilité-qualité-de-code--déploiement-conteneurisé)
13. [Tableau Synthétique des Fonctionnalités pour le Rapport](#13-tableau-synthétique-des-fonctionnalités-pour-le-rapport)

---

## 1. Introduction & Contexte du Stage

### 1.1 Problématique Métier
La **Direction Générale des Ressources en Eau (DGRE)** gère le réseau hydrométrique et pluviométrique national tunisien, composé de centaines de stations de mesure réparties sur les 24 gouvernorats. Traditionnellement, l'exploitation de ces données souffrait de plusieurs verrous :
- Des bases hétérogènes réparties entre fichiers **Microsoft Access (.mdb)** propriétaires et feuilles Excel décentralisées dans les 24 Commissariats Régionaux au Développement Agricole (**CRDA**).
- Des délais considérables (plusieurs mois) pour compiler, critiquer, interpoler et publier l'**Annuaire Pluviométrique National annuel**.
- La nécessité pour les cadres hydrologues de maîtriser des logiciels SIG complexes (ArcGIS, QGIS) et le langage SQL pour la moindre requête cartographique.

### 1.2 Solution Apportée par CartaGen
CartaGen modernise ce flux métier en introduisant une **plateforme web multi-agents pilotée par l'Intelligence Artificielle générative** capable de :
1. Comprendre les requêtes des hydrologues en **langage naturel** (ex: *"Carte d'isohyètes de l'hiver 2018 à Béja"*).
2. Extraire et agréger les données dans une base unifiée **PostgreSQL / PostGIS** (`dgre_db`).
3. Générer et exécuter du code Python scientifique pour produire des **cartes d'isohyètes normalisées**.
4. Éditer automatiquement l'**Annuaire Officiel de 80+ pages au format PDF/LaTeX**, conforme à la charte institutionnelle de la DGRE.

---

## 2. Vue d'Ensemble de l'Architecture

CartaGen adopte les principes de la **Clean Architecture (Architecture Hexagonale)** :

```
cartagen/
├── domain/                               # Couche Métier pure (Entités, Modèles, Bus d'événements)
│   └── models/map_request.py, agent_message_bus.py
│
└── infrastructure/                       # Couche Infrastructure & Adaptateurs
    ├── agents/                           # Orchestrateur, Agents SQL, SIG, RAG, Audit
    │   └── skeletons/                    # Templates de code géospatial réutilisables
    ├── api/                              # Routes FastAPI, WebSockets, Frontend statique
    ├── config.py                         # Configuration Pydantic BaseSettings
    ├── database/                         # Connecteur PostgreSQL, Ingestion MDB/Shapefiles, Zvec
    ├── logging/                          # Logger structuré rotatif & collecteur LoRA
    ├── providers/                        # Abstraction des LLM (Cloud, Colab, Local)
    └── sandbox/                          # Exécution sous-processus & Validateur AST
```

---

## 3. Module 1 : Système Multi-Agents Collaboratif (Supervisor Pattern)

### Feature 1.1 : Orchestrateur Délibératif Central (`CartaGenOrchestrator`)
- **Rôle** : Chef d'orchestre supervisant le cycle de vie complet de chaque requête utilisateur.
- **Fonctionnement** : Analyse la demande, sollicite la base vectorielle Zvec pour enrichir le contexte, délègue la traduction SQL à l'agent SQL, fait auditer les données par l'agent d'audit, pilote la génération du script SIG, et gère la boucle de rétroaction en cas d'erreur.
- **Fichier** : [`cartagen/infrastructure/agents/orchestrator.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/orchestrator.py)

### Feature 1.2 : Bus de Messages Inter-Agents (`AgentMessageBus`)
- **Rôle** : Canal de communication découplé permettant aux agents d'échanger des messages typés (`sender`, `receiver`, `content`, `timestamp`).
- **Fonctionnement** : Historise toutes les étapes du raisonnement multi-agents et les retransmet en direct au Frontend pour une transparence totale de l'IA (*Explainable AI*).
- **Fichier** : [`cartagen/domain/models/agent_message_bus.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/domain/models/agent_message_bus.py)

### Feature 1.3 : Agent Générateur SQL Sécurisé (`SQLGeneratorAgent`)
- **Rôle** : Traducteur sémantique du langage naturel vers PostgreSQL / PostGIS.
- **Fonctionnement** :
  - **Stratégie hybride prioritaire** : Interroge d'abord le modèle fine-tuné LoRA via `ProviderManager` en JSON strict (`{"sql_query": ..., "target_col": ...}`).
  - **Parseur déterministe de secours (Fallback)** : En cas d'indisponibilité réseau, bascule instantanément sur un moteur de règles Python analysant les entités temporelles et spatiales via expressions régulières.
  - **Sanitisation SQL native** : Nettoie toute entrée utilisateur via `_sanitize_sql_string` et valide les gouvernorats contre une liste blanche stricte.
- **Fichier** : [`cartagen/infrastructure/agents/sql_generator_agent.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/sql_generator_agent.py)

### Feature 1.4 : Agent Générateur de Code SIG (`SIGGeneratorAgent`)
- **Rôle** : Générateur de scripts Python scientifiques spécialisés en géomatique.
- **Fonctionnement** : Reçoit la requête SQL validée et la colonne cible, charge le squelette approprié via `skeleton_loader`, injecte les directives spatiales et produit un script autonome avec GeoPandas, Matplotlib et SciPy.
- **Fichier** : [`cartagen/infrastructure/agents/sig_generator_agent.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/sig_generator_agent.py)

### Feature 1.5 : Agent d'Audit et de Cohérence des Données (`DataAuditAgent`)
- **Rôle** : Contrôleur qualité vérifiant les données brutes avant tout rendu cartographique.
- **Fonctionnement** : Vérifie qu'au moins 3 stations disposent de coordonnées et de valeurs pluviométriques non nulles pour permettre une interpolation spatiale valide. Détecte les valeurs aberrantes ($> 500\text{ mm}$ en 24h) et les lacunes chroniques.
- **Fichier** : [`cartagen/infrastructure/agents/data_audit_agent.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/data_audit_agent.py)

### Feature 1.6 : Agent RAG Conversationnel pour Annuaires (`AnnuaireRAGAgent`)
- **Rôle** : Agent d'assistance documentaire répondant aux questions des utilisateurs sur l'historique pluviométrique en exploitant les pages des annuaires indexés.
- **Fonctionnement** : Recherche vectorielle avec re-ranking, synthèse textuelle et citation de sources (documents, pages exactes, tableaux).
- **Fichier** : [`cartagen/infrastructure/agents/annuaire_rag_agent.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/annuaire_rag_agent.py)

---

## 4. Module 2 : RAG Sémantique & Moteur Vectoriel In-Process (Zvec)

### Feature 2.1 : Indexation Vectorielle Multi-Collections (`VectorManager`)
- **Rôle** : Moteur de base de données vectorielle embarqué ultraléger ne nécessitant aucun serveur externe lourd.
- **Fonctionnement** : Gère 4 collections Zvec indépendantes : `stations_index`, `schemas_index`, `annuaires_index`, `images_index` avec indexation HNSW et métrique cosinus.
- **Fichier** : [`cartagen/infrastructure/database/vector_manager.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/database/vector_manager.py)

### Feature 2.2 : Chunks Hybrides Enrichis de Métadonnées
- **Rôle** : Préservation du contexte spatial et temporel lors de la découpe documentaire.
- **Fonctionnement** : Chaque chunk textuel est préfixé d'un en-tête structuré `[META: doc_name='...', page=...]` permettant au LLM d'identifier la provenance exacte de l'information.

### Feature 2.3 : Filtrage Temporel Strict & Boost Spatial (+30%)
- **Rôle** : Élimination des hallucinations sur les années et focalisation géographique.
- **Fonctionnement** : Si l'utilisateur demande l'année 2018, les chunks d'autres années sont filtrés. Si un gouvernorat est mentionné, son score de similarité vectorielle est boosté de 30% pour remonter en tête de prompt.

### Feature 2.4 : Synthèses Macro-Analytiques Intégrées
- **Rôle** : Réponse instantanée aux questions globales sans recalcul lourd.
- **Fonctionnement** : L'index Zvec stocke des fiches de synthèse pré-calculées contenant les records nationaux de pluie (maxima absolus, minima, moyennes régionales historiques).

### Feature 2.5 : Ré-Indexation Asynchrone lors de Nouveaux Imports
- **Rôle** : Synchronisation continue des données.
- **Fonctionnement** : L'ingestion d'un nouveau fichier MDB ou Shapefile déclenche en tâche de fond (`BackgroundTasks`) l'actualisation vectorielle sans bloquer l'API.

---

## 5. Module 3 : Cartographie Géospatiale & Algorithmes Hydrologiques

### Feature 5.1 : Interpolation Spatiale IDW (Inverse Distance Weighting)
- **Rôle** : Modélisation continue de la hauteur de pluie sur l'ensemble du territoire tunisien.
- **Algorithme** :
  $$Z(x) = \frac{\sum_{i=1}^{m} w_i(x) Z_i}{\sum_{i=1}^{m} w_i(x)} \quad \text{avec} \quad w_i(x) = \frac{1}{d(x, x_i)^2}$$
- **Optimisation** : Implémentation vectorisée avec un arbre de recherche k-dimensionnel (`scipy.spatial.cKDTree`) sur une grille régulière de 400×800 points, garantissant une exécution en moins d'une seconde.

### Feature 5.2 : Calcul des Lames d'Eau par Polygones de Thiessen (Voronoi)
- **Rôle** : Calcul officiel DGRE des moyennes régionales et nationales pondérées par les surfaces d'influence des stations.
- **Algorithme** :
  $$P_R = \sum_{i} P_i \times w_i^R \quad \text{où} \quad w_i^R = \frac{\text{Aire}(\text{Polygone}_i \cap \text{Région}_R)}{\text{Aire}(\text{Région}_R)}$$
- **Fichier de documentation** : [`explication_methode_thiessen.md`](file:///d:/Desktop/stage_dgre/carta_gen/explication_methode_thiessen.md)

### Feature 5.3 : Projection Conforme Officielle UTM 32N (`EPSG:32632`)
- **Rôle** : Respect des normes cartographiques nationales de l'OTC (Office de la Topographie et du Cadastre).
- **Fonctionnement** : Les coordonnées géographiques (WGS84 `EPSG:4326`) sont reprojetées dynamiquement en coordonnées métriques planes UTM 32N pour éviter toute déformation des distances lors de l'interpolation.

### Feature 5.4 : Échelle de Couleurs & Niveaux Normalisés DGRE
- **Rôle** : Lisibilité immédiate et standardisée des cartes selon l'horizon temporel.
- **Paliers de précipitations** :
  - Relevés journaliers ($<1\text{ mois}$) : $0, 5, 10, 20, 30, 50, 75, 100, 150\text{ mm}$.
  - Relevés mensuels/saisonniers : $0, 20, 50, 75, 100, 150, 200, 250, 350\text{ mm}$.
  - Relevés annuels : $0, 50, 100, 200, 400, 600, 800, 1000, 1200\text{ mm}$.
- **Palette** : 8 couleurs standardisées allant du rouge (sécheresse) au bleu foncé intense (fortes pluies).

### Feature 5.5 : Cartographie Différentielle (Variation Interannuelle)
- **Rôle** : Visualisation du gain ou de la perte de pluviosité entre deux années successives ($P_{N} - P_{N-1}$).
- **Palette** : Carte divergente bichromatique (Brun/Orange pour le déficit, Bleu/Vert pour l'excédent).

### Feature 5.6 : Cartographie des Rapports à la Normale (%) et Anomalies
- **Rôle** : Suivi de la sécheresse météorologique.
- **Calcul** : Rapport de la pluie observée sur la normale trentenaire fixe issue de `moy_interannuelle`.

### Feature 5.7 : Cartographie des 6 Grandes Régions Naturelles
- **Rôle** : Synthèse géographique par zone bioclimatique :
  *Nord Ouest, Nord Est, Centre Ouest, Centre Est, Sud Ouest, Sud Est*.
- **Fonctionnement** : Découpage spatial et calcul des moyennes régionales intégrées dans la synthèse nationale.

---

## 6. Module 4 : Architecture des Squelettes Modulaires (Skeletons System)

### Feature 6.1 : Découplage en 9 Templates `.py.template` Autonomes
- **Rôle** : Résolution de la dette technique du fichier monolithique de 1 586 lignes.
- **Structure** :
  - [`mono.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/mono.py.template) : Carte nationale d'isohyètes standard.
  - [`analysis.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/analysis.py.template) : Carte couplée à un tableau récapitulatif HTML.
  - [`single_gouv.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/single_gouv.py.template) : Zoom et masque spatial centré sur un seul gouvernorat.
  - [`compare_gouv.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/compare_gouv.py.template) : Comparaison multi-gouvernorats côte à côte.
  - [`region_hydro.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/region_hydro.py.template) : Découpage par bassins versants / régions hydrographiques.
  - [`difference.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/difference.py.template) : Carte d'écart entre deux millésimes.
  - [`anomalie.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/anomalie.py.template) : Pourcentage par rapport à la moyenne historique.
  - [`stations_density.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/stations_density.py.template) : Carte de semis et maillage des stations actives.
  - [`region_naturelle.py.template`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/region_naturelle.py.template) : Découpage des 6 zones bioclimatiques.

### Feature 6.2 : Chargeur Centralisé avec Cache LRU (`skeleton_loader.py`)
- **Rôle** : Évite les lectures disque répétées lors de sollicitations intensives de l'API.
- **Fonctionnement** : Fonction `@lru_cache(maxsize=20)` maintenant les templates en mémoire RAM.
- **Fichier** : [`cartagen/infrastructure/agents/skeletons/skeleton_loader.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/agents/skeletons/skeleton_loader.py)

---

## 7. Module 5 : Édition Automatisée des Annuaires Pluviométriques Officiels

### Feature 7.1 : Générateur Complet d'Annuaires en LaTeX/PDF
- **Rôle** : Automatisation complète du livrable phare de la DGRE (document officiel de 80+ pages).
- **Structure du document généré** :
  1. **Page de garde officielle** avec armoiries de la République, logos ministériels, adresses et téléphones officiels.
  2. **Avant-propos institutionnel** rappelant le rôle des 24 CRDA et de la Direction des Ressources en Eau.
  3. **Aperçu sommaire sur la pluviosité** généré dynamiquement avec analyse textuelle des faits marquants de l'année.
  4. **Tableau 1** : Synthèse comparative des pluies régionales calculées par Thiessen avec les normales.
  5. **Tableau 2** : Historique sur les 8 dernières années dans `pluies_148` avec alerte automatique sur les années lacunaires.
  6. **Table des matières, liste des figures et des tableaux**.
  7. **Cartes d'isohyètes mensuelles et annuelles haute résolution** insérées directement dans le document.
  8. **Relevés journaliers détaillés** station par station.
- **Fichier** : [`generer_annuaire_database.py`](file:///d:/Desktop/stage_dgre/carta_gen/generer_annuaire_database.py)

### Feature 7.2 : Ligne de Commande (CLI) pour l'Édition Nationale et Régionale
- **Rôle** : Utilisation par batch pour les ingénieurs préférant le terminal.
- **Exemples d'utilisation** :
  ```bash
  python generer_annuaire_database.py --year 2018 --gouv all --output Annuaire_National_2018_2019.pdf
  python generer_annuaire_database.py --year 2021 --gouv Beja --output Annuaire_Beja_2021_2022.pdf
  ```

---

## 8. Module 6 : Sécurité & Environnement d'Exécution Isolé (Sandbox Manager)

### Feature 8.1 : Validateur Statique de Code AST (`CodeSecurityValidator`)
- **Rôle** : Détection et neutralisation proactive des codes Python malveillants générés par le LLM avant exécution.
- **Règles d'interdiction strictes** :
  - **Modules système/réseau bloqués** : `subprocess`, `socket`, `shutil`, `http`, `urllib`, `ctypes`, `threading`, `signal`, `pickle`.
  - **Fonctions d'exécution dynamique bloquées** : `eval`, `exec`, `compile`, `__import__`, `globals`, `locals`, `getattr`.
  - **Appels OS destructeurs bloqués** : `os.system`, `os.popen`, `os.remove`, `os.unlink`, `os.rmdir`, `os.rename`.
- **Fichier** : [`cartagen/infrastructure/sandbox/sandbox_manager.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/sandbox/sandbox_manager.py)

### Feature 8.2 : Exécution Isolée en Sous-Processus avec Timeout
- **Rôle** : Confinement de l'exécution du code SIG.
- **Fonctionnement** : Chaque script est écrit dans un sous-dossier éphémère (`sandbox_runs/<UUID>/`), exécuté via `subprocess.run` avec un **timeout strict de 60 secondes** empêchant tout gel du serveur par boucle infinie.

### Feature 8.3 : Boucle d'Auto-Correction LLM (Refinement Loop)
- **Rôle** : Résilience face aux erreurs de code générées.
- **Fonctionnement** : Si le script échoue (code de retour différent de 0 ou image non produite), l'erreur Python (Traceback) est interceptée et renvoyée à `SIGGeneratorAgent.correct_code()`. Le LLM répare le code et la Sandbox retente l'exécution (jusqu'à 3 itérations).

### Feature 8.4 : Protection Anti-Injection SQL Déterministe
- **Rôle** : Sécurisation absolue des requêtes construites depuis le langage naturel.
- **Fonctionnement** :
  - Fonction `_sanitize_sql_string()` éliminant les commentaires SQL (`--`), les caractères non autorisés et doublant les guillemets simples (`'`).
  - Validation des filtres géographiques sur la liste blanche des 24 gouvernorats officiels.
  - Remplacement de toutes les concaténations de chaînes dans `postgres_connection.py` par des requêtes paramétrées avec `%s`.

### Feature 8.5 : Protection Anti-Path Traversal
- **Rôle** : Sécurisation du téléchargement des images et des annuaires PDF.
- **Fonctionnement** : Extraction stricte du nom de fichier via `os.path.basename()`, vérification canonique de l'arborescence autorisée (`startswith(sandbox_dir)`), et restriction stricte aux extensions prévues (`.png`, `.pdf`).

### Feature 8.6 : Contrôle CORS Configurable
- **Rôle** : Restriction des accès navigateur non autorisés.
- **Fonctionnement** : Middleware FastAPI paramétré via la variable d'environnement `ALLOWED_ORIGINS` avec restriction aux méthodes `GET` et `POST`.

---

## 9. Module 7 : Gestionnaire Unifié de Modèles d'Intelligence Artificielle

### Feature 9.1 : Abstraction Multi-Providers (`ProviderManager`)
- **Rôle** : Élimination de la duplication de code LLM entre agents et découplage total du fournisseur d'IA.
- **Fournisseurs pris en charge** :
  - **Cloud Ultra-rapide** : Groq (`llama-3.3-70b-versatile`), OpenRouter (`meta-llama/llama-3.1-8b-instruct`), OpenAI (`gpt-4o-mini`).
  - **Modèles Distants Fine-Tunés** : Google Colab (vLLM / Ngrok), Kaggle GPU (VisCoder2-7B).
  - **Modèles Locaux Déconnectés** : Ollama (`localhost:11434`), exécution locale PyTorch 4-bit (Transformers).
- **Fichier** : [`cartagen/infrastructure/providers/provider_manager.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/providers/provider_manager.py)

### Feature 9.2 : Normalisation ChatML et Robustesse Tunnel Ngrok
- **Rôle** : Garantie d'une sortie JSON stricte et franchissement transparent des passerelles de tunneling.
- **Fonctionnement** : Encapsulation automatique dans le format ChatML (`<|im_start|>system...`) pour les petits modèles locaux, et injection des en-têtes `ngrok-skip-browser-warning` et `Bypass-Tunnel-Remainder`.

---

## 10. Module 8 : Ingestion des Données & Pipeline de Fine-Tuning LoRA

### Feature 10.1 : Ingestion Automatisée des Bases Access MDB/ACCDB (`MdbIngestionService`)
- **Rôle** : Migration fluide des données historiques des CRDA vers PostgreSQL.
- **Fonctionnement** : Connexion via `pyodbc` / `mdbtools`, détection automatique du gouvernorat d'origine, nettoyage des dates et insertion incrémentale dans la table `pluies_148`.
- **Fichier** : [`cartagen/infrastructure/database/mdb_ingest.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/database/mdb_ingest.py)

### Feature 10.2 : Ingestion des Couches Spatiales Shapefiles (`ShapefileIngestionService`)
- **Rôle** : Initialisation des contours géographiques PostGIS.
- **Fonctionnement** : Lecture des Shapefiles (`limite_pays_polygon`, `gouvernorats`), contrôle des systèmes de coordonnées et écriture en base avec géométries PostGIS valides.
- **Fichier** : [`cartagen/infrastructure/database/shapefile_ingest.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/database/shapefile_ingest.py)

### Feature 10.3 : Collecteur Continu de Données LoRA (`DatasetCollector`)
- **Rôle** : Apprentissage continu (*Continuous Learning*).
- **Fonctionnement** : Sauvegarde chaque interaction utilisateur réussie au format JSONL ChatML dans `lora_dataset_collector/lora_reinforced_dataset.jsonl` pour enrichir les futures sessions de ré-entraînement.
- **Fichier** : [`cartagen/infrastructure/logging/dataset_collector.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/logging/dataset_collector.py)

### Feature 10.4 : Datasets de Fine-Tuning Optimisés & Partitionnés
- **Dataset Mixte Global** : [`dataset_mixed_clean.jsonl`](file:///d:/Desktop/stage_dgre/carta_gen/dataset_finetuning/dataset_mixed_clean.jsonl) (**1 302 exemples**).
- **Dataset Dédié SQL** : [`dataset_sql_lora.jsonl`](file:///d:/Desktop/stage_dgre/carta_gen/dataset_finetuning/dataset_sql_lora.jsonl) (**877 exemples** en JSON strict).
- **Dataset Dédié SIG** : [`dataset_sig_lora.jsonl`](file:///d:/Desktop/stage_dgre/carta_gen/dataset_finetuning/dataset_sig_lora.jsonl) (**425 scripts Python** GeoPandas).
- **Caractéristiques de qualité** : 38.7% d'exemples enrichis de RAG, équilibre parfait des 24 gouvernorats, couverture des 4 saisons et des années hydrologiques.

### Feature 10.5 : Script d'Entraînement Google Colab QLoRA (`train_colab_unsloth.py`)
- **Rôle** : Fine-tuning rapide et gratuit de Llama-3.1-8B sur GPU T4 Colab via **Unsloth** (durée : ~15 minutes, empreinte VRAM réduite de 70%).
- **Fichier** : [`dataset_finetuning/train_colab_unsloth.py`](file:///d:/Desktop/stage_dgre/carta_gen/dataset_finetuning/train_colab_unsloth.py)

---

## 11. Module 9 : API REST Asynchrone & Interface Frontend Interactive

### Feature 11.1 : API Asynchrone Haute Performance (FastAPI)
- **Rôle** : Exposition des fonctionnalités du système sous forme d'API web moderne, documentée automatiquement via Swagger UI (`/docs`).
- **Principaux Endpoints** :
  - `POST /api/v1/maps/generate` : Soumission asynchrone d'une demande de carte (retourne un `request_id`).
  - `GET /api/v1/maps/status/{request_id}` : Polling temps réel de l'état d'avancement et des traces d'agents.
  - `GET /api/v1/maps/image/{filename}` : Récupération de l'image haute résolution générée.
  - `POST /api/v1/yearbook/generate` : Déclenchement de l'édition d'un annuaire PDF.
  - `GET /api/v1/yearbook/download/{filename}` : Téléchargement du document officiel PDF.
  - `POST /api/v1/annuaire/chat` : Dialogue documentaire avec l'agent RAG.
  - `POST /api/v1/data/ingest-mdb` : Téléversement et ingestion d'un fichier Access.
  - `GET /api/v1/providers` : Liste des modèles d'IA disponibles.
- **Fichier** : [`cartagen/infrastructure/api/app.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/api/app.py)

### Feature 11.2 : Interface Frontend Web Intuitive & Réactive
- **Rôle** : Point d'accès visuel pour les agents de la DGRE sans compétence informatique particulière.
- **Fonctionnalités du Frontend** :
  - Zone de saisie en langage naturel et formulaire de sélection guidée (Année, Mois, Saison, Gouvernorat).
  - Visualiseur de cartes interactif avec zoom et téléchargement HD.
  - Affichage en direct du terminal multi-agents montrant les délibérations de chaque agent.
  - Onglet dédié à la génération d'annuaires officiels avec prévisualisation des PDF.
  - Panneau de configuration des fournisseurs LLM.
- **Fichiers** : [`index.html`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/api/static/index.html), [`style.css`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/api/static/style.css), [`app.js`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/api/static/app.js)

---

## 12. Module 10 : Observabilité, Qualité de Code & Déploiement Conteneurisé

### Feature 12.1 : Logging Structuré avec Rotation Automatique (`logger.py`)
- **Rôle** : Traçabilité complète des opérations sans saturation de l'espace disque.
- **Fonctionnement** : Fichiers journaux rotatifs (`logs/cartagen.log`, max 5 Mo, conservation de 3 sauvegardes historiques) et formatage horodaté standardisé.
- **Fichier** : [`cartagen/infrastructure/logging/logger.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/logging/logger.py)

### Feature 12.2 : Configuration Typée Centralisée Pydantic (`config.py`)
- **Rôle** : Validation stricte des paramètres d'environnement au démarrage de l'application via Pydantic `BaseSettings`.
- **Fichier** : [`cartagen/infrastructure/config.py`](file:///d:/Desktop/stage_dgre/carta_gen/cartagen/infrastructure/config.py)

### Feature 12.3 : Banc de Tests Automatisés (24 Tests Unitaires & d'Intégration)
- **Rôle** : Garantie de non-régression et validation continue de la sécurité.
- **Couverture des tests** :
  - `test_sql_sanitizer.py` : Neutralisation des injections SQL, dédoublement des apostrophes, rejet des scripts.
  - `test_security_validator.py` : Blocage des modules dangereux (`subprocess`, `socket`, `eval`, `exec`, `os.system`).
  - `test_skeleton_loader.py` : Intégrité des 9 squelettes et validation des coordonnées `x`/`y`.
  - `test_config.py` : Validation des paramètres de configuration et connexion BDD.
  - `test_api_security.py` : Protection Path Traversal sur tous les endpoints de téléchargement et validation CORS.
- **Résultat** : 100% de réussite (24 tests passés en 0.05 seconde).
- **Dossier** : [`tests/`](file:///d:/Desktop/stage_dgre/carta_gen/tests/)

### Feature 12.4 : Déploiement Conteneurisé Docker & Docker Compose
- **Rôle** : Portabilité totale et reproductibilité de l'environnement de production.
- **Composants conteneurisés** :
  - `postgres_db` : Conteneur PostgreSQL 15 avec extension spatiale PostGIS 3.3 et healthcheck automatique.
  - `cartagen_app` : Conteneur applicatif Python 3.11 avec GDAL, TeX Live et MDBTools préinstallés.
- **Fichiers** : [`Dockerfile`](file:///d:/Desktop/stage_dgre/carta_gen/Dockerfile), [`docker-compose.yml`](file:///d:/Desktop/stage_dgre/carta_gen/docker-compose.yml)

---

## 13. Tableau Synthétique des Fonctionnalités pour le Rapport

Ce tableau récapitulatif peut être directement inséré dans le chapitre de conception ou de réalisation de votre rapport de stage :

| N° | Fonctionnalité | Module / Fichier Source | Technologies Clés | Valeur Ajoutée pour la DGRE |
| :---: | :--- | :--- | :--- | :--- |
| **F01** | Orchestration Multi-Agents délibérative | `CartaGenOrchestrator` | Python, Pattern Supervisor | Automatisation de bout en bout sans intervention manuelle. |
| **F02** | Bus de messages inter-agents traçable | `AgentMessageBus` | Dataclasses, Event-Driven | Transparence et explicabilité du raisonnement de l'IA (*XAI*). |
| **F03** | Traduction Text-to-SQL avec fallback | `SQLGeneratorAgent` | PostgreSQL, Regex, JSON | Traduction instantanée des requêtes en requêtes BDD optimales. |
| **F04** | Générateur de code géospatial modulaire | `SIGGeneratorAgent` | Python, Matplotlib, GeoPandas | Production autonome de cartes isohyètes professionnelles. |
| **F05** | Audit automatique de validité des stations | `DataAuditAgent` | SQL, Statistiques spatiales | Élimination des interpolations erronées sur stations vides. |
| **F06** | RAG documentaire pour annuaires | `AnnuaireRAGAgent` | Zvec, NLP, Cosine Similarity | Recherche sémantique dans l'historique des publications DGRE. |
| **F07** | Moteur vectoriel in-process embarqué | `VectorManager` | Zvec, HNSW, Vector Embeddings | RAG performant sans infrastructure serveur lourde. |
| **F08** | Interpolation spatiale IDW haute vitesse | `mono.py.template` | SciPy `cKDTree`, NumPy | Calcul de grille d'isohyètes en moins d'une seconde. |
| **F09** | Intégration spatiale de Thiessen (Voronoi)| `generer_annuaire_database.py` | Shapely, Voronoi Diagrams | Calcul officiel des lames d'eau régionales et nationales. |
| **F10** | Reprojection cartographique officielle | Squelettes SIG | PostGIS, EPSG:32632 (UTM 32N) | Conformité rigoureuse avec les cartes officielles tunisiennes. |
| **F11** | Palettes thématiques normalisées DGRE | Squelettes SIG | Matplotlib `BoundaryNorm` | Échelles de couleurs standardisées (journalier/mensuel/annuel). |
| **F12** | Cartographie des anomalies et normales | `anomalie.py.template` | GeoPandas, moy_interannuelle | Suivi instantané des déficits pluviométriques et sécheresses. |
| **F13** | Squelettes de code avec cache mémoire | `skeleton_loader.py` | Python `@lru_cache`, Templates | Temps de réponse divisé et réduction massive de la dette technique. |
| **F14** | Édition automatisée d'annuaires PDF | `generer_annuaire_database.py` | LaTeX, PDFLaTeX, Jinja2 | Passage d'un délai de production de 3 mois à 2 minutes. |
| **F15** | Détection automatique des lacunes 8 ans | `generer_annuaire_database.py` | Python, Pandas, PostgreSQL | Signalement transparent des stations en panne ou lacunaires. |
| **F16** | Analyse statique de code AST dans Sandbox | `CodeSecurityValidator` | Python `ast`, Static Analysis | Blocage préventif des codes malveillants avant exécution. |
| **F17** | Confinement Sandbox avec Timeout 60s | `SandboxManager` | `subprocess`, Isolation OS | Protection contre les gels serveur et boucles infinies. |
| **F18** | Boucle d'auto-correction de code LLM | `SIGGeneratorAgent` | Feedback Loop, AI Correction | Résilience opérationnelle : le système répare son propre code. |
| **F19** | Sanitisation SQL & Whitelist spatiale | `sql_generator_agent.py` | Regex, Whitelisting, Param SQL | Immunité totale contre les injections SQL sur la base DGRE. |
| **F20** | Protection contre le Path Traversal | `app.py` | `os.path.basename`, Canonical | Impossibilité pour un utilisateur de lire des fichiers système. |
| **F21** | Gestionnaire unifié de providers IA | `ProviderManager` | Requests, REST, ChatML | Flexibilité totale : bascule instantanée entre Cloud et Local. |
| **F22** | Ingestion automatisée de fichiers MDB | `MdbIngestionService` | `pyodbc`, `mdbtools`, PostGIS | Valorisation immédiate des bases historiques Access des CRDA. |
| **F23** | Collecteur de données LoRA en continu | `DatasetCollector` | JSONL, LoRA Formatting | Amélioration continue du modèle avec l'usage réel des agents. |
| **F24** | Datasets de fine-tuning enrichis | `dataset_generator.py` | ChatML, 1 302 exemples | Modèle spécialisé maîtrisant les 24 gouvernorats et 4 saisons. |
| **F25** | Entraînement QLoRA 4-bit optimisé | `train_colab_unsloth.py` | Unsloth, PEFT, TRL, Colab | Entraînement d'un modèle 8B paramètres en 15 minutes sur GPU gratuit. |
| **F26** | API Web Asynchrone documentée | `app.py` | FastAPI, Pydantic, Swagger UI | Intégration facile avec d'autres systèmes ministériels. |
| **F27** | Interface Web interactive pour non-initiés | Frontend statique | HTML5, Vanilla CSS, JS | Prise en main immédiate sans compétences en programmation. |
| **F28** | Logging structuré avec rotation 5 Mo | `logger.py` | Python `RotatingFileHandler` | Traçabilité de niveau production sans saturation du disque. |
| **F29** | Configuration typée et centralisée | `config.py` | Pydantic `BaseSettings`, .env | Robustesse au déploiement et détection immédiate des erreurs d'env. |
| **F30** | Suite de tests automatisés (24 tests) | `tests/` | Python `unittest`, TestClient | Assurance qualité logicielle et non-régression validée à 100%. |
| **F31** | Conteneurisation complète en production | Docker & Compose | Docker, PostGIS, Uvicorn | Déploiement "en un clic" sur n'importe quel serveur ou VM DGRE. |

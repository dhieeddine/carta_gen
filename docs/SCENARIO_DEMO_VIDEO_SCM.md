# Scénario Détaillé & Script Vidéo de Démonstration (Sujet 10 : SCM)
## *Architecture Logicielle — Logging, Versioning & Gestion des Conflits sur CartaGen*

Ce document constitue le **guide de tournage minuté (4 à 5 minutes)** pour enregistrer votre vidéo de présentation du projet d'Architecture Logicielle.

---

## 🎬 Résumé des Séquences & Timing

| Séquence | Durée | Volet SCM Illustré | Actions Clés à l'Écran |
| :---: | :---: | :--- | :--- |
| **1** | **00:00 - 00:30** | **Introduction** | Présentation du sujet n°10, des 3 volets et de CartaGen. |
| **2** | **00:30 - 01:45** | **Volet 1 : Logging & Audit** | Structured JSON, Correlation ID, Sensitive Data Masking, Audit SHA-256. |
| **3** | **01:45 - 02:45** | **Volet 2 : Versioning** | SemVer 2.0 (v1.2.0), Migrations Alembic PostGIS, CI/CD GitHub Actions. |
| **4** | **02:45 - 04:15** | **Volet 3 : Gestion des Conflits** | Démo Git 3-Way Merge (`git_conflict_lab.py`) + OCC Concurrence HTTP 409. |
| **5** | **04:15 - 05:00** | **Conclusion & Tests** | Exécution des 26 tests automatisés (0.295s) et conclusion finale. |

---

## 🎥 Déroulé Chronologique Détaillé (Script & Voix-Off)

### Séquence 1 : Introduction & Cadrage (00:00 – 00:30)

* **Visuel à l'écran :**
  * Ouvrez la page d'accueil de CartaGen sur votre navigateur (`http://localhost:8000`) ou affichez le document [`RAPPORT_ARCHITECTURE_SCM_SUJET10.md`](file:///D:/Desktop/Architecture_Logiciel/RAPPORT_ARCHITECTURE_SCM_SUJET10.md).
* **Ce que vous dites :**
  > *"Bonjour à tous. Dans cette vidéo, je vous présente les réalisations effectuées dans le cadre du sujet numéro 10 d'Architecture Logicielle, portant sur la Gestion de la Configuration Logicielle (SCM).*
  > *Ce sujet impose d'explorer trois volets fondamentaux : la journalisation, la gestion des versions et la gestion des conflits.*
  > *Pour confronter ces concepts théoriques à un système réel et complexe, nous avons intégré l'ensemble de ces fonctionnalités sur la plateforme hydrologique et cartographique intelligente CartaGen, développée pour la Direction Générale des Ressources en Eau."*

---

### Séquence 2 : Volet 1 — Journalisation (Logging) & Audit (00:30 – 01:45)

* **Visuel à l'écran :**
  1. Ouvrez dans VS Code le fichier [`cartagen/infrastructure/logging/logger.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/logging/logger.py).
  2. Ouvrez le fichier de logs actif [`logs/cartagen.log`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/logs/cartagen.log).
  3. Ouvrez le registre d'audit [`logs/audit_trail.jsonl`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/logs/audit_trail.jsonl).
* **Actions à montrer :**
  - **Structured JSON & Correlation ID :** Pointez une ligne de log dans `logs/cartagen.log`. Montrez que le log n'est plus du texte brut, mais un objet JSON structuré contenant l'horodatage UTC, le niveau `INFO`, et surtout le **`correlation_id`** (géré via `contextvars`).
  - **Masquage des Secrets :** Montrez la classe `SensitiveDataFilter` qui remplace automatiquement les clés privées (`HF_TOKEN`, `GROQ_API_KEY`) par `***MASKED***`.
  - **Audit Trail Immuable :** Dans `logs/audit_trail.jsonl`, montrez que chaque action sensible (modification d'environnement, mutation de configuration) est consignée avec une empreinte cryptographique **`checksum_sha256`** certifiant son intégrité.
* **Ce que vous dites :**
  > *"Dans une architecture multi-agents asynchrone comme CartaGen, il est indispensable de pouvoir corréler tous les événements déclenchés par une même requête.*
  > *Nous avons donc mis en place un Structured JSON Logger conforme aux standards Cloud-Native. Chaque requête HTTP reçoit un Correlation ID unique propagé à travers tous les agents asynchrones.*
  > *De plus, un filtre de sécurité anonymise automatiquement les jetons d'API et mots de passe, tandis qu'un registre d'audit certifié par empreinte SHA-256 garantit la traçabilité infalsifiable des opérations critiques."*

---

### Séquence 3 : Volet 2 — Gestion des Versions (Versioning) (01:45 – 02:45)

* **Visuel à l'écran :**
  1. Dans votre terminal ou dans Swagger UI (`http://localhost:8000/docs`), exécutez `GET /api/v1/version`.
  2. Affichez le dossier [`cartagen/infrastructure/database/migrations/versions/`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/database/migrations/versions/).
  3. Affichez le workflow CI/CD [`.github/workflows/ci.yml`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/.github/workflows/ci.yml).
* **Actions à montrer :**
  - **SemVer 2.0 :** Montrez la réponse JSON : `"version": "1.2.0"`, `"codename": "Hydrologic-SCM"`, liée au commit Git actif (`f5ba213`).
  - **Migrations de Base de Données (Alembic) :** Montrez les scripts de migration `001_initial_pluvio_schema.py` et `002_add_audit_and_optimistic_locking.py`. Expliquez les méthodes `upgrade()` et `downgrade()`.
  - **CI/CD :** Montrez les étapes du pipeline GitHub Actions (Flake8 linting, validation de la réversibilité Alembic, tests unitaires, build Docker).
* **Ce que vous dites :**
  > *"Pour le deuxième volet, nous avons abandonné la version figée dans le code au profit d'un Semantic Versioning 2.0 synchronisé avec nos tags Git. La version actuelle est la 1.2.0.*
  > *Un point crucial en architecture logicielle est l'évolution synchronisée du code et de la base de données. Nous avons donc intégré Alembic pour versionner le schéma PostgreSQL/PostGIS de manière incrémentale et bidirectionnelle.*
  > *Enfin, un workflow GitHub Actions valide automatiquement la qualité du code, la conformité des migrations et l'exécution des tests à chaque intégration."*

---

### Séquence 4 : Volet 3 — Gestion des Conflits (02:45 – 04:15) ⭐ *(Point Clé)*

*Cette séquence est divisée en deux démonstrations complémentaires : au niveau du code, puis au niveau des données.*

#### 4.1 Démonstration du Conflit de Code Source Git (02:45 – 03:30)
* **Action :** Dans le terminal, tapez et exécutez la commande :
  ```powershell
  & "D:\Desktop\stage_dgre\carta_gen\venv\Scripts\python.exe" git_conflict_lab.py
  ```
* **Ce qui se passe :** Le laboratoire s'exécute en direct :
  - Création de deux branches concurrentes (`feature/redis-cache` et `feature/memory-cache`).
  - Détection automatique du conflit par Git (`CONFLICT (content)`).
  - Affichage des marqueurs textuels de conflit `<<<<<<< HEAD` et `>>>>>>>`.
  - Résolution synthétique hybride et affichage du graphe DAG final.
* **Ce que vous dites :**
  > *"Au niveau de l'équipe de développement, la gestion des divergences est démontrée ici via notre laboratoire Git. Deux développeurs modifient simultanément les mêmes paramètres de cache sur deux branches distinctes. Lors de la fusion, Git intercepte le conflit. Le système décortique les marqueurs et nous appliquons une résolution synthétique qui préserve l'historique sous forme de graphe propre."*

#### 4.2 Démonstration du Conflit de Données au Runtime (03:30 – 04:15)
* **Action :** Dans Swagger UI (`http://localhost:8000/docs`) ou via le script [`test_live_api.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/test_live_api.py) :
  - Effectuez un `PUT /api/v1/config/versioned/station_demo` avec `expected_version: 1` $\rightarrow$ Réponse `200 OK` (la version passe à `2`).
  - Recommencez immédiatement avec `expected_version: 1` $\rightarrow$ Le serveur renvoie instantanément **`HTTP 409 Conflict`** (`OptimisticLockConflictError`).
* **Ce que vous dites :**
  > *"Au niveau de l'exécution et des données, nous avons implémenté le patron de Verrouillage Optimiste (OCC). Si un deuxième utilisateur tente de sauvegarder une station ou une configuration avec un numéro de version devenu obsolète, le système bloque la transaction pour éviter le problème critique de la mise à jour perdue (Lost Update) et renvoie un code standard HTTP 409 Conflict consigné dans l'audit."*

---

### Séquence 5 : Conclusion & Validation par les Tests (04:15 – 05:00)

* **Visuel à l'écran :**
  * Dans le terminal PowerShell, lancez la commande globale des tests :
  ```powershell
  & "D:\Desktop\stage_dgre\carta_gen\venv\Scripts\python.exe" -m unittest tests/test_scm_features.py tests/test_security_validator.py tests/test_sql_sanitizer.py
  ```
* **Résultat affiché :**
  ```text
  Ran 26 tests in 0.295s
  OK
  ```
* **Ce que vous dites pour conclure :**
  > *"Pour certifier la fiabilité de l'ensemble, nous disposons d'une suite de 26 tests automatisés validant à 100% le Correlation ID, le masquage des secrets, la détection des conflits de concurrence et la sécurité de la sandbox en moins de 300 millisecondes.*
  > *Grâce à ces apports, CartaGen répond aux normes professionnelles les plus strictes de la Gestion de Configuration Logicielle. Merci pour votre attention."*

---

## 🛠️ Commandes Prêtes pour le Tournage

Avant d'appuyer sur le bouton d'enregistrement (ex: avec OBS Studio ou `Win + Alt + R`), préparez vos fenêtres :

### Terminal 1 (Serveur en arrière-plan) :
```powershell
cd D:\Desktop\Architecture_Logiciel\carta_gen
$env:PYTHONPATH = "D:\Desktop\Architecture_Logiciel\carta_gen"
& "D:\Desktop\stage_dgre\carta_gen\venv\Scripts\python.exe" run_app.py
```

### Terminal 2 (Démonstrations en direct) :
```powershell
cd D:\Desktop\Architecture_Logiciel\carta_gen
$env:PYTHONPATH = "D:\Desktop\Architecture_Logiciel\carta_gen"
$PYTHON = "D:\Desktop\stage_dgre\carta_gen\venv\Scripts\python.exe"

# Démo Conflit Git :
& $PYTHON git_conflict_lab.py

# Démo Live API SCM :
& $PYTHON test_live_api.py

# Validation Complète des Tests :
& $PYTHON -m unittest tests/test_scm_features.py tests/test_security_validator.py tests/test_sql_sanitizer.py
```

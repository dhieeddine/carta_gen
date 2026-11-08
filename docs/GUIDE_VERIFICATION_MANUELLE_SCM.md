# Guide de Vérification Manuelle Pas-à-Pas (Sujet 10 : SCM)
## *Architecture Logicielle — Logging, Versioning & Gestion des Conflits sur CartaGen*

Ce guide détaille **la procédure exacte pour tester et valider manuellement**, une par une et en ligne de commande, toutes les nouvelles fonctionnalités architecturales développées sur le projet **CartaGen**.

---

## 📌 Prérequis & Initialisation du Terminal

Ouvrez un terminal PowerShell dans le répertoire racine du projet :

```powershell
cd D:\Desktop\Architecture_Logiciel\carta_gen
$env:PYTHONPATH = "D:\Desktop\Architecture_Logiciel\carta_gen"
$PYTHON = "D:\Desktop\stage_dgre\carta_gen\venv\Scripts\python.exe"
```

> **Astuce :** Ces 3 variables préparent l'environnement virtuel et les chemins d'import Python sans toucher à vos variables d'environnement système permanentes.

---

## 📋 Sommaire des Tests Manuels

1. [Volet 1 : Journalisation (Logging) & Audit](#1-volet-1--journalisation-logging--audit)
   - [Test 1.1 : Structured JSON Logging & Correlation ID](#test-11--structured-json-logging--correlation-id)
   - [Test 1.2 : Masquage Automatique des Secrets (Data Masking)](#test-12--masquage-automatique-des-secrets-data-masking)
   - [Test 1.3 : Registre d'Audit Immuable & Checksum SHA-256](#test-13--registre-daudit-immuable--checksum-sha-256)
   - [Test 1.4 : Middleware ASGI de Traçabilité HTTP](#test-14--middleware-asgi-de-traçabilité-http)
2. [Volet 2 : Gestion des Versions (Versioning)](#2-volet-2--gestion-des-versions-versioning)
   - [Test 2.1 : Versioning Sémantique (SemVer 2.0.0 & Git Hash)](#test-21--versioning-sémantique-semver-200--git-hash)
   - [Test 2.2 : Découverte des Migrations de Schéma (Alembic)](#test-22--découverte-des-migrations-de-schéma-alembic)
   - [Test 2.3 : Validation Locale du Pipeline CI/CD GitHub Actions](#test-23--validation-locale-du-pipeline-cicd-github-actions)
3. [Volet 3 : Gestion des Conflits (Conflict Management)](#3-volet-3--gestion-des-conflits-conflict-management)
   - [Test 3.1 : Démonstrateur Interactif de Conflit Git (Code Source)](#test-31--démonstrateur-interactif-de-conflit-git-code-source)
   - [Test 3.2 : Verrouillage Optimiste (OCC & Rejet Concurrence HTTP 409)](#test-32--verrouillage-optimiste-occ--rejet-concurrence-http-409)
   - [Test 3.3 : Verrouillage Pessimiste / Mutex de Tâches Batch](#test-33--verrouillage-pessimiste--mutex-de-tâches-batch)
4. [Exécution Globale de la Suite de Tests (26 Tests)](#4-exécution-globale-de-la-suite-de-tests)

---

## 1. Volet 1 : Journalisation (Logging) & Audit

### Test 1.1 : Structured JSON Logging & Correlation ID
* **Objectif :** Vérifier que chaque événement de log est émis sous format JSON structuré et que le `correlation_id` est correctement injecté via le contexte asynchrone (`contextvars`).

* **Commande à exécuter :**
```powershell
& $PYTHON -c "
from cartagen.infrastructure.logging import setup_logger, correlation_id_ctx, current_user_ctx

# 1. Définition du contexte asynchrone (simulation d'une requête arrivant sur un agent)
correlation_id_ctx.set('req_dgre_test_8888')
current_user_ctx.set('ingenieur_hydrologue')

# 2. Émission d'un log via le logger configuré
logger = setup_logger('cartagen.test_demo')
logger.info('Test d execution manuelle du logger JSON avec correlation ID !')
"
```

* **Résultat attendu :**
Une ligne JSON valide s'affiche dans le terminal, contenant les champs `timestamp` (ISO UTC), `correlation_id: req_dgre_test_8888`, `user: ingenieur_hydrologue`, et le message formaté.

---

### Test 1.2 : Masquage Automatique des Secrets (Data Masking)
* **Objectif :** Vérifier que le filtre de sécurité [`SensitiveDataFilter`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/logging/logger.py) intercepte et masque automatiquement les clés d'API sensibles (`GROQ_API_KEY`, `HF_TOKEN`, mots de passe, tokens Bearer).

* **Commande à exécuter :**
```powershell
& $PYTHON -c "
from cartagen.infrastructure.logging import setup_logger

logger = setup_logger('cartagen.security_demo')

# Tentative d'impression de logs contenant des secrets privés
logger.info('Tentative d appel avec GROQ_API_KEY=gsk_SecretGroqKey999888777666555444333222111 et HF_TOKEN=hf_HuggingFaceSecretToken999888777')
"
```

* **Résultat attendu :**
Dans le JSON émis, les secrets doivent être remplacés par `***MASKED***` :
```text
"message": "Tentative d appel avec GROQ_API_KEY=\"***MASKED***\" et HF_TOKEN=hf_***MASKED***"
```

---

### Test 1.3 : Registre d'Audit Immuable & Checksum SHA-256
* **Objectif :** Vérifier que la classe [`AuditLogger`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/logging/audit_logger.py) écrit une ligne d'audit certifiée par empreinte cryptographique SHA-256 dans `logs/audit_trail.jsonl`.

* **Commande à exécuter :**
```powershell
& $PYTHON -c "
from cartagen.infrastructure.logging import AuditLogger, correlation_id_ctx

correlation_id_ctx.set('req_audit_demo_42')
audit = AuditLogger()

# Enregistrement d'une action critique (ex: modification du modèle LLM actif)
event = audit.log_event(
    action='MUTATION_SYSTEM_CONFIG',
    resource='config:LLM_PROVIDER',
    status='SUCCESS',
    ip_address='192.168.1.50',
    previous_state={'provider': 'groq', 'model': 'llama-3.3-70b'},
    new_state={'provider': 'openrouter', 'model': 'qwen2.5-coder'},
    details={'motif': 'Maintenance serveur'}
)

print('=== Événement d Audit Généré ===')
import pprint
pprint.pprint(event)
"
```

* **Vérification du fichier généré :**
```powershell
Get-Content logs/audit_trail.jsonl -Tail 1
```

* **Résultat attendu :**
L'enregistrement contient un champ `checksum_sha256` de 64 caractères hexadécimaux garantissant l'intégrité de la piste d'audit.

---

### Test 1.4 : Middleware ASGI de Traçabilité HTTP
* **Objectif :** Vérifier que le middleware [`CorrelationIdMiddleware`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/logging/middleware.py) intercepte les requêtes HTTP, extrait ou injecte le `X-Request-ID` et calcule la latence `X-Response-Time-Ms`.

* **Commande à exécuter :**
```powershell
& $PYTHON -c "
import asyncio
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse
from cartagen.infrastructure.logging import CorrelationIdMiddleware

# Création d'une micro-application FastAPI de test
app = FastAPI()
app.add_middleware(CorrelationIdMiddleware)

@app.get('/api/test-trace')
async def test_trace():
    return {'status': 'ok', 'service': 'CartaGen SCM'}

# Simulation d'un appel ASGI direct
async def run_asgi():
    scope = {
        'type': 'http',
        'method': 'GET',
        'path': '/api/test-trace',
        'headers': [(b'x-request-id', b'req_custom_client_12345')],
        'query_string': b''
    }
    
    received_headers = {}
    async def send(msg):
        if msg['type'] == 'http.response.start':
            for k, v in msg['headers']:
                received_headers[k.decode()] = v.decode()

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    await app(scope, receive, send)
    print('En-têtes HTTP de réponse injectés :')
    for k, v in received_headers.items():
        print(f'  {k}: {v}')

asyncio.run(run_asgi())
"
```

* **Résultat attendu :**
La sortie affiche :
```text
x-request-id: req_custom_client_12345
x-response-time-ms: <durée en millisecondes>
```

---

## 2. Volet 2 : Gestion des Versions (Versioning)

### Test 2.1 : Versioning Sémantique (SemVer 2.0.0 & Git Hash)
* **Objectif :** Vérifier que le module central [`cartagen/version.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/version.py) retourne les métadonnées de version conformes à SemVer 2.0 synchronisées avec le tag Git.

* **Commande à exécuter :**
```powershell
& $PYTHON -c "
from cartagen.version import get_version_metadata
import pprint

print('=== Métadonnées de Version CartaGen ===')
pprint.pprint(get_version_metadata())
"
```

* **Vérification du tag Git :**
```powershell
git tag -n
git log -1 --oneline
```

* **Résultat attendu :**
La version affichée est `1.2.0`, le codename est `Hydrologic-SCM`, le tag Git est `v1.2.0`, et le hash de commit correspond exactement au dernier commit Git `f5ba213`.

---

### Test 2.2 : Découverte des Migrations de Schéma (Alembic)
* **Objectif :** Vérifier que les scripts de migration de schéma PostgreSQL / PostGIS sont correctement détectés, ordonnés et inspectés par [`DatabaseMigrationManager`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/database/migrations/migration_manager.py).

* **Commande à exécuter :**
```powershell
& $PYTHON "cartagen/infrastructure/database/migrations/migration_manager.py"
```

* **Résultat attendu :**
Le script liste les 2 révisions chaînées :
```text
=== Alembic Migrations enregistrées (2) ===
[001_initial_schema] 001_initial_pluvio_schema (Revises: None)
[002_audit_and_locking] 002_add_audit_and_optimistic_locking (Revises: 001_initial_schema)
```

---

### Test 2.3 : Validation Locale du Pipeline CI/CD GitHub Actions
* **Objectif :** Simuler sur votre machine le pipeline d'intégration continue configuré dans [`.github/workflows/ci.yml`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/.github/workflows/ci.yml).

* **Commandes à exécuter :**
```powershell
# 1. Vérification de la syntaxe Python (Flake8)
& $PYTHON -m flake8 cartagen/version.py cartagen/infrastructure/concurrency cartagen/infrastructure/logging --count --select=E9,F63,F7,F82 --show-source --statistics

# 2. Validation de l'intégrité SemVer
& $PYTHON -c "from cartagen.version import get_version_metadata; assert get_version_metadata()['semver'] == '1.2.0'; print('✓ SemVer CI Check: PASS')"

# 3. Validation de l'arborescence des migrations
& $PYTHON -c "from cartagen.infrastructure.database.migrations.migration_manager import DatabaseMigrationManager; mgr = DatabaseMigrationManager(); assert len(mgr.get_available_revisions()) >= 2; print('✓ Migrations CI Check: PASS')"
```

* **Résultat attendu :**
Zéro erreur syntaxique et affichage des messages `PASS`.

---

## 3. Volet 3 : Gestion des Conflits (Conflict Management)

### Test 3.1 : Démonstrateur Interactif de Conflit Git (Code Source)
* **Objectif :** Exécuter le laboratoire pédagogique de conflit de fusion Git créé spécialement pour la soutenance.

* **Commande à exécuter :**
```powershell
& $PYTHON "git_conflict_lab.py"
```

* **Ce qui se passe en direct :**
1. Un dépôt Git temporaire et isolé est créé.
2. Le Développeur A crée la branche `feature/redis-cache` et modifie les paramètres de cache.
3. Le Développeur B crée la branche `feature/memory-cache` et modifie les **mêmes lignes**.
4. La commande `git merge` est déclenchée : Git détecte automatiquement le conflit (`CONFLICT (content)`).
5. Le script extrait et affiche les marqueurs textuels de conflit :
   ```python
   <<<<<<< HEAD
   CACHE_STRATEGY = 'in_memory_lru'
   =======
   CACHE_STRATEGY = 'redis_cluster_v2'
   >>>>>>> feature/redis-cache
   ```
6. Le script applique l'arbitrage architectural (stratégie hybride `hybrid_lru_then_redis`).
7. Le commit de merge est finalisé et le graphe de branches Git (DAG) s'affiche à l'écran.

---

### Test 3.2 : Verrouillage Optimiste (OCC & Rejet Concurrence HTTP 409)
* **Objectif :** Démontrer concrètement la prévention du problème de mise à jour perdue (*Lost Update Problem*) via [`OptimisticLockManager`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/concurrency/optimistic_lock.py).

* **Commande à exécuter :**
```powershell
& $PYTHON -c "
from cartagen.infrastructure.concurrency import OptimisticLockManager, OptimisticLockConflictError

occ = OptimisticLockManager()
res_id = 'station_ain_draham_148'

# 1. État initial (Version 1)
print('[Étape 1] Lecture de la station :')
doc1 = occ.register_or_get(res_id, {'nom': 'Ain Draham', 'seuil_alerte_mm': 100})
print(f'  Station: {doc1[\"data\"][\"nom\"]} | Version: {doc1[\"version\"]} | ETag: {doc1[\"etag\"]}')

# 2. L\'hydrologue A modifie avec succès en soumettant la version 1 attendue
print('\n[Étape 2] Hydrologue A enregistre sa modification (attend v1) :')
doc2 = occ.update_resource(res_id, {'nom': 'Ain Draham', 'seuil_alerte_mm': 120}, expected_version=1, user='hydrologue_A')
print(f'  ✓ Succès ! Nouvelle Version: {doc2[\"version\"]} | ETag: {doc2[\"etag\"]}')

# 3. L\'hydrologue B tente d\'enregistrer en se basant sur la version 1 devenue OBSOLÈTE
print('\n[Étape 3] Hydrologue B tente de modifier en soumettant l ancienne version 1 :')
try:
    occ.update_resource(res_id, {'nom': 'Ain Draham', 'seuil_alerte_mm': 90}, expected_version=1, user='hydrologue_B')
    print('  ERREUR : Le conflit n a pas été détecté !')
except OptimisticLockConflictError as exc:
    print(f'  🚨 CONFLIT DÉTECTÉ ET BLOQUÉ (Code HTTP 409 Conflict) :')
    print(f'  {exc.message}')
"
```

* **Résultat attendu :**
L'Étape 3 intercepte le conflit, protège les données contre l'écrasement silencieux, et consigne l'incident dans `logs/audit_trail.jsonl`.

---

### Test 3.3 : Verrouillage Pessimiste / Mutex de Tâches Batch
* **Objectif :** Démontrer l'exclusion mutuelle stricte sur les tâches lourdes non fractionnables via [`TaskMutexManager`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/concurrency/pessimistic_lock.py).

* **Commande à exécuter :**
```powershell
& $PYTHON -c "
from cartagen.infrastructure.concurrency import TaskMutexManager, JobAlreadyRunningError

mutex = TaskMutexManager()
task = 'ingestion_base_access_beja_2024'

# 1. Le premier processus acquiert le verrou
print('[1] Processus 1 tente d acquérir le verrou...')
mutex.acquire_lock(task, owner='worker_node_alpha', timeout_seconds=60)
print('  ✓ Verrou acquis avec succès !')

# 2. Le deuxième processus tente d exécuter la même tâche simultanément
print('[2] Processus 2 tente d acquérir le même verrou en parallèle...')
try:
    mutex.acquire_lock(task, owner='worker_node_beta', timeout_seconds=60)
    print('  ERREUR : Double exécution non empêchée !')
except JobAlreadyRunningError as exc:
    print(f'  🚨 CONFLIT REJETÉ (HTTP 409 Conflict) :')
    print(f'  {exc}')

# 3. Libération du verrou
print('[3] Processus 1 termine sa tâche et libère le verrou...')
mutex.release_lock(task)
print('  ✓ Verrou libéré. Nouvelles exécutions désormais autorisées.')
"
```

* **Résultat attendu :**
Le deuxième processus est rejeté avec l'exception `JobAlreadyRunningError`, empêchant la corruption des données par collision de tâches.

---

## 4. Exécution Globale de la Suite de Tests

Pour lancer l'ensemble des **26 tests automatisés** couvrant à la fois les 3 volets SCM et la sécurité applicative de CartaGen :

```powershell
& $PYTHON -m unittest `
    "tests/test_scm_features.py" `
    "tests/test_security_validator.py" `
    "tests/test_sql_sanitizer.py" `
    "tests/test_skeleton_loader.py" `
    "tests/test_config.py"
```

### Résultat attendu :
```text
Ran 26 tests in 0.295s

OK
```

---

## 5. Fichiers et Chemins Clés Référencés

| Volet | Fichier Source | Description |
| :--- | :--- | :--- |
| **Volet 1 (Logging)** | [`cartagen/infrastructure/logging/logger.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/logging/logger.py) | Formateur JSON, SensitiveDataFilter, rotation 5 Mo |
| **Volet 1 (Logging)** | [`cartagen/infrastructure/logging/audit_logger.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/logging/audit_logger.py) | Registre d'audit immuable avec hachage SHA-256 |
| **Volet 1 (Logging)** | [`cartagen/infrastructure/logging/middleware.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/logging/middleware.py) | Middleware ASGI X-Request-ID et timing |
| **Volet 2 (Versioning)** | [`cartagen/version.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/version.py) | Métadonnées SemVer 2.0.0 et commit Git |
| **Volet 2 (Versioning)** | [`alembic.ini`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/alembic.ini) & [`migrations/`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/database/migrations/) | Scripts de migration PostGIS 001 et 002 |
| **Volet 2 (Versioning)** | [`.github/workflows/ci.yml`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/.github/workflows/ci.yml) | Pipeline GitHub Actions automatisé |
| **Volet 3 (Conflits)** | [`cartagen/infrastructure/concurrency/optimistic_lock.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/concurrency/optimistic_lock.py) | Verrouillage optimiste (OCC / HTTP 409) |
| **Volet 3 (Conflits)** | [`cartagen/infrastructure/concurrency/pessimistic_lock.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/cartagen/infrastructure/concurrency/pessimistic_lock.py) | Mutex applicatif avec TTL |
| **Volet 3 (Conflits)** | [`git_conflict_lab.py`](file:///D:/Desktop/Architecture_Logiciel/carta_gen/git_conflict_lab.py) | Démonstrateur interactif de 3-way merge Git |
| **Rapport de Synthèse** | [`RAPPORT_ARCHITECTURE_SCM_SUJET10.md`](file:///D:/Desktop/Architecture_Logiciel/RAPPORT_ARCHITECTURE_SCM_SUJET10.md) | Rapport académique pour l'enseignant |

# CartaGen - DGRE

CartaGen est une application multi-agents permettant de générer automatiquement des cartes d'isohyètes, des graphiques statistiques et des analyses de données pluviométriques à partir des bases de données de la Direction Générale des Ressources en Eau (DGRE).

---

## 🚀 Fonctionnalités Clés
1. **Génération de Cartes Spatialisées** : Interpolation IDW de haute précision des données pluviométriques sous forme de cartes d'isohyètes avec contouring et masquage selon les frontières tunisiennes.
2. **Analyse de Données & Graphiques (Nouveau)** : Capacité de générer des graphiques (courbes, histogrammes, graphiques en barres) et des tableaux de statistiques directement depuis un prompt en langage naturel.
3. **Recherche Sémantique avec Zvec (Nouveau)** : Indexation sémantique in-process des stations de mesure et des schémas de table pour réaliser du RAG (Retrieval-Augmented Generation) sur l'Agent SQL, évitant ainsi les hallucinations de noms ou de structures de tables.
4. **Système Auto-Correctif (Refinement Loop)** : Un Agent Qualité détecte les erreurs d'exécution de code Python dans la Sandbox et applique des corrections à la volée.

---

## 🛠️ Architecture Multi-Agents (Pattern Supervisor)
L'application repose sur un orchestrateur supervisant les agents suivants :
* **SQL Generator Agent (Text-to-SQL RAG Dynamique)** : Reçoit le prompt utilisateur enrichi par le contexte sémantique de **Zvec DB**, puis interroge le LLM actif (ex: Groq Llama 3.3) pour générer dynamiquement la requête SQL optimale et identifier précisément la colonne cible (sans aucune règle rigide).
* **SIG/Rendu Generator Agent** : Rédige le script Python géospatial ou statistique nécessaire.
* **Sandbox Manager** : Exécute le script généré dans un environnement sécurisé et isolé.
* **Quality Agent** : Analyse les logs d'erreurs et régénère le code corrigé si nécessaire.

---

## 📦 Installation & Prérequis

### Dépendances principales
* Python 3.10 à 3.13
* PostgreSQL / PostGIS (stockant `yasra_data`, `stations_base`, `pluies`, etc.)
* Packages requis : `fastapi`, `geopandas`, `zvec`, `sentence-transformers`, `matplotlib`, `pandas`.

Installez les dépendances :
```bash
pip install -r requirements.txt
```

---

## 🔄 Ingestion & Recherche Vectorielle Zvec
Pour initialiser et synchroniser la base vectorielle locale Zvec avec PostgreSQL :

```bash
python sync_zvec_db.py
```
Ce script effectue :
1. L'extraction des stations depuis `stations_base`.
2. La vectorisation sémantique des noms, bassins et localités via le modèle `all-MiniLM-L6-v2`.
3. L'indexation sémantique des descriptions des schémas de tables.
4. La persistance locale de l'index dans le dossier `./zvec_store/`.

---

## 🖥️ Démarrage de l'Application

Lancez le serveur local de développement :
```bash
python run_app.py
```
L'interface web moderne est disponible à l'adresse : **`http://localhost:8000/`**.

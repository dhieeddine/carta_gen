# 🖼️ Guide des Figures et Illustrations pour le Rapport de Stage (DGRE)
## Recommandations Visuelles, Légendes et Méthodes de Génération

> **Objectif** : Ce guide liste l'ensemble des figures indispensables pour structurer, aérer et professionnaliser votre rapport de stage ou Projet de Fin d'Études (PFE). Un bon rapport d'ingénieur doit être richement illustré pour faciliter la lecture du jury et prouver la rigueur scientifique de vos travaux.

---

## 📑 Sommaire des Figures Proposées (17 Figures Clés)

1. [Chapitre 1 : Contexte, Problématique & Données](#1-chapitre-1--contexte-problématique--données-dgre)
2. [Chapitre 2 : Architecture & Coopération Multi-Agents](#2-chapitre-2--architecture-système--pipeline-multi-agents)
3. [Chapitre 3 : Modélisation Mathématique & Algorithmes SIG](#3-chapitre-3--modélisation-mathématique--algorithmes-sig)
4. [Chapitre 4 : Entraînement de l'IA & Fine-Tuning LoRA](#4-chapitre-4--apprentissage-automatique--fine-tuning-lora)
5. [Chapitre 5 : Sécurité & Environnement d'Exécution Isolé](#5-chapitre-5--sécurité--isolation-sandbox)
6. [Chapitre 6 : Résultats Expérimentaux, Interface & Livrables](#6-chapitre-6--interface-utilisateur--rendus-cartographiques-finaux)

---

## 1. Chapitre 1 : Contexte, Problématique & Données DGRE

### 📍 Figure 1.1 : Répartition Spatiale des 148 Stations Pluviométriques Nationales
- **Description** : Carte de la Tunisie affichant les points de mesure des 148 stations retenues, superposées au découpage administratif des 24 gouvernorats.
- **Pourquoi l'inclure ?** : Montre la disparité de densité du réseau d'observation (forte densité au Nord humide, maillage plus lâche dans le Sud saharien).
- **Légende type** : *« Figure 1.1 : Réseau pluviométrique officiel de la DGRE composé de 148 stations de référence (Projection UTM 32N / EPSG:32632). »*
- **Source / Génération** : Peut être générée directement avec le template `stations_density.py.template` ou depuis QGIS.

### 🗺️ Figure 1.2 : Découpage des 6 Grandes Régions Naturelles de Tunisie
- **Description** : Carte thématique avec 6 couleurs distinctes délimitant les zones bioclimatiques de référence : *Nord Ouest, Nord Est, Centre Ouest, Centre Est, Sud Ouest, Sud Est*.
- **Pourquoi l'inclure ?** : Ces régions constituent l'unité d'analyse fondamentale de l'annuaire pour les calculs de bilans hydrologiques.
- **Légende type** : *« Figure 1.2 : Les 6 Régions Naturelles de la Tunisie utilisées par la DGRE pour le calcul des moyennes régionales pondérées. »*
- **Fichier déjà disponible dans le projet** : [`test_region_naturelle.png`](file:///d:/Desktop/stage_dgre/carta_gen/test_region_naturelle.png)

### 🗄️ Figure 1.3 : Modèle Entité-Association (Schéma de la Base de Données `dgre_db`)
- **Description** : Diagramme du schéma relationnel PostgreSQL/PostGIS montrant les tables `station_148`, `pluies_148`, `moy_interannuelle`, `gouvernorats`, `limite_pays_polygon` avec leurs clés primaires, clés étrangères et index géospatiaux GiST.
- **Pourquoi l'inclure ?** : Démontre la transition réussie depuis les fichiers hétérogènes MS Access `.mdb` vers un SGBD spatialisé moderne.
- **Légende type** : *« Figure 1.3 : Schéma relationnel et spatial de la base de données unifiée PostgreSQL/PostGIS dgre_db. »*

---

## 2. Chapitre 2 : Architecture Système & Pipeline Multi-Agents

### 🏗️ Figure 2.1 : Architecture Globale Hexagonale (Clean Architecture)
- **Description** : Schéma en couches concentriques montrant la séparation stricte :
  - *Core Domain* (Modèles de requête, Bus de messages).
  - *Application & Agents* (Orchestrateur, Agent SQL, Agent SIG, Agent RAG).
  - *Infrastructure & Adaptateurs* (PostgreSQL, Zvec, Providers LLM, Sandbox, FastAPI).
- **Légende type** : *« Figure 2.1 : Architecture hexagonale (Ports & Adapters) de la plateforme CartaGen garantissant la maintenabilité et l'indépendance technologique. »*

### 🔄 Figure 2.2 : Diagramme d'Activité du Cycle Multi-Agents Délibératif
- **Description** : Diagramme de flux complet illustrant les interactions entre l'utilisateur, l'orchestrateur central, le RAG Zvec, l'Agent SQL, l'Agent d'Audit, l'Agent SIG, le Sandbox et la boucle de correction.
- **Légende type** : *« Figure 2.2 : Diagramme d'activité séquentiel illustrant la chaîne de délibération et d'auto-correction multi-agents (Supervisor Pattern). »*
- **Fichier prêt à l'emploi** : [`diagramme_activite_cartagen.png`](file:///d:/Desktop/stage_dgre/carta_gen/diagramme_activite_cartagen.png) (généré par [`generate_activity_diagram_png.py`](file:///d:/Desktop/stage_dgre/carta_gen/generate_activity_diagram_png.py)).

### 🧠 Figure 2.3 : Architecture Interne du RAG Sémantique In-Process (Zvec)
- **Description** : Schéma de flux montrant la transformation de la requête naturelle :
  $$\text{Requête} \rightarrow \text{Embedding (All-MiniLM-L6-v2)} \rightarrow \text{Recherche HNSW Cosine} \rightarrow \text{Filtrage Année} \rightarrow \text{Boost Spatial (+30\%)} \rightarrow \text{Injection Prompt}.$$
- **Légende type** : *« Figure 2.3 : Pipeline de recherche sémantique hybride dans Zvec avec filtrage temporel strict et pondération géographique. »*

---

## 3. Chapitre 3 : Modélisation Mathématique & Algorithmes SIG

### 📐 Figure 3.1 : Principe Mathématique de l'Interpolation Spatiale IDW
- **Description** : Schéma 2D/3D illustrant la grille d'interpolation et la décroissance du poids en $1/d^2$ par rapport aux stations environnantes.
- **Pourquoi l'inclure ?** : Justifie mathématiquement le choix de l'IDW vectorisé par rapport au Krigeage ordinaire pour le temps réel.
- **Légende type** : *« Figure 3.1 : Principe de l'interpolation spatiale par pondération inverse de la distance (IDW) appliquée aux observations pluviométriques. »*

### 🔷 Figure 3.2 : Diagramme des Polygones de Thiessen (Voronoi) Découpés
- **Description** : Découpage de Voronoi sur l'ensemble de la Tunisie avec superposition des frontières régionales pour montrer les aires d'influence $w_i^R$.
- **Pourquoi l'inclure ?** : Explique visuellement comment est calculée la hauteur de lame d'eau officielle dans le Tableau 1 de l'Annuaire.
- **Légende type** : *« Figure 3.2 : Intégration spatiale par les polygones de Thiessen (Voronoi) pour le calcul des pluviométries régionales pondérées par la superficie. »*

### 🎨 Figure 3.3 : Échelle Hypsométrique & Nuancier Officiel DGRE
- **Description** : Tableau visuel des 8 couleurs standardisées avec leurs codes hexadécimaux et leurs intervalles selon la période ($<1\text{ mois}$, mensuel/saisonnier, annuel).
- **Légende type** : *« Figure 3.3 : Charte graphique et échelle de discrétisation officielle de la DGRE pour les isohyètes (du rouge déficit au bleu excédent). »*

---

## 4. Chapitre 4 : Apprentissage Automatique & Fine-Tuning LoRA

### ⚙️ Figure 4.1 : Architecture d'Entraînement LoRA (Low-Rank Adaptation)
- **Description** : Schéma de décomposition matricielle $W = W_0 + \Delta W = W_0 + B \times A$ avec rang $r=16$, montrant que le modèle de base 8B reste gelé en 4-bit pendant que seuls les adaptateurs sont entraînés.
- **Légende type** : *« Figure 4.1 : Mécanisme d'adaptation à faible rang (LoRA) appliqué aux matrices d'attention du modèle de base Llama-3.1-8B. »*

### 📊 Figure 4.2 : Distribution des Données d'Entraînement Avant et Après Correction
- **Description** : Graphique à barres comparatif montrant :
  - L'intégration des 4 saisons (0 $\rightarrow$ 108 exemples).
  - La présence du contexte RAG (0% $\rightarrow$ 38.7%).
  - L'équilibrage des 24 gouvernorats (0 mention sur Béja/Gabès/Kébili/Médenine $\rightarrow$ 60+ mentions chacun).
- **Légende type** : *« Figure 4.2 : Analyse comparative de la distribution du dataset de fine-tuning (dataset_mixed_clean.jsonl) avant et après rééquilibrage. »*

### 📉 Figure 4.3 : Courbe de Perte d'Entraînement (Training Loss Curve)
- **Description** : Graphique extrait de TensorBoard ou Wandb montrant la décroissance de la perte d'entraînement (Loss) au cours des époques dans Google Colab.
- **Légende type** : *« Figure 4.3 : Évolution de la fonction de perte (SFT Loss) au cours de l'entraînement LoRA sous Google Colab avec Unsloth. »*

---

## 5. Chapitre 5 : Sécurité & Isolation Sandbox

### 🛡️ Figure 5.1 : Arbre Syntaxique Abstrait (AST) et Filtrage Proactif
- **Description** : Schéma représentant un nœud d'arbre syntaxique Python (`ast.Import`, `ast.Call`) et montrant comment le validateur `CodeSecurityValidator` bloque les branches contenant `subprocess` ou `eval`.
- **Légende type** : *« Figure 5.1 : Mécanisme d'analyse statique de l'AST interceptant les instructions non autorisées avant l'exécution dans la Sandbox. »*

### 🔁 Figure 5.2 : Cycle de la Boucle d'Auto-Correction (Refinement Loop)
- **Description** : Diagramme montrant le cycle :
  $$\text{Code généré} \rightarrow \text{Sandbox} \rightarrow \text{Erreur détectée (stderr)} \rightarrow \text{Prompt d'Auto-Correction} \rightarrow \text{Code réparé} \rightarrow \text{Succès}.$$
- **Légende type** : *« Figure 5.2 : Algorithme de la boucle d'auto-correction permettant au système multi-agents de réparer dynamiquement ses propres erreurs d'exécution. »*

---

## 6. Chapitre 6 : Interface Utilisateur & Rendus Cartographiques Finaux

### 🖥️ Figure 6.1 : Capture d'Écran de l'Interface Web CartaGen
- **Description** : Vue d'ensemble de l'interface graphique : champ de prompt en langage naturel, logs des agents en temps réel, panneau de contrôle des gouvernorats et visualiseur de cartes.
- **Légende type** : *« Figure 6.1 : Interface web de la plateforme CartaGen avec affichage transparent de la délibération multi-agents en direct. »*

### 🗺️ Figure 6.2 : Carte d'Isohyètes Annuelle Haute Résolution Générée par l'IA
- **Description** : Rendu cartographique final d'une carte annuelle (ex: Année 2021-2022) avec contours des gouvernorats, étiquettes, rose des vents, échelle et légende officielle.
- **Légende type** : *« Figure 6.2 : Carte d'isohyètes nationale haute résolution (300 DPI) produite automatiquement par CartaGen en projection UTM 32N. »*

### 📉 Figure 6.3 : Carte d'Anomalie Pluviométrique (% de la Normale Historique)
- **Description** : Carte illustrant les zones en déficit critique ($<50\%$) et les zones excédentaires ($>150\%$).
- **Légende type** : *« Figure 6.3 : Carte d'anomalie spatiale exprimant le rapport à la moyenne historique trentenaire pour l'année 2022. »*

### 📖 Figure 6.4 : Aperçu de l'Annuaire Pluviométrique Officiel (PDF / LaTeX)
- **Description** : Montage visuel montrant :
  1. La page de garde officielle avec armoiries.
  2. Le Tableau 1 (comparatif régional Thiessen).
  3. Une page de carte d'isohyètes insérée.
- **Légende type** : *« Figure 6.4 : Extrait de l'Annuaire Pluviométrique National édité automatiquement au format PDF conforme à la charte DGRE. »*

---

## 💡 Conseils Pratiques pour l'Insertion dans votre Rapport (LaTeX / Word)

1. **Format d'image recommandé** :
   - Pour les schémas et captures : utilisez le format **PNG** (avec une résolution minimale de 300 DPI) ou **PDF vectoriel**.
2. **Exemple d'insertion en LaTeX** :
   ```latex
   \begin{figure}[htbp]
       \centering
       \includegraphics[width=0.85\textwidth]{figures/diagramme_activite_cartagen.png}
       \caption{Diagramme d'activité séquentiel illustrant la chaîne de délibération et d'auto-correction multi-agents.}
       \label{fig:activite_multiagents}
   \end{figure}
   ```
3. **Appel dans le texte** :
   - Ne laissez jamais une figure sans explication. Écrivez toujours : *"Comme l'illustre la Figure 2.2, l'orchestrateur supervise..."*.

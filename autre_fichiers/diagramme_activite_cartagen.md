# Diagramme d'Activité Globale — Plateforme CartaGen (DGRE)

Ce document présente le diagramme d'activité officiel modélisant le flux de traitement complet de l'application **CartaGen**, depuis la réception de la requête utilisateur sur l'interface Web jusqu'à l'affichage de la carte, du graphique ou du rapport hydro-climatique.

---

## 🎨 Rendu Visuel Graphique (PNG)

![Diagramme d'Activité Globale CartaGen](file:///C:/Users/LENOVO/.gemini/antigravity-ide/brain/092451f4-e6c7-408e-acf2-af3b9eff0b21/diagramme_activite_cartagen.png)

---

## 📊 Diagramme d'Activité UML (Mermaid)

```mermaid
stateDiagram-v2
    [*] --> ReceptionRequete : L'utilisateur soumet une requête (Chat RAG ou Carte SIG)
    
    state ReceptionRequete {
        [*] --> AnalyseOption : Extraction de la question & options (Provider LLM, RAG Activé/Désactivé)
    }

    RequeteVisual: Question de type Carte / Graphique Visuel ?
    ReceptionRequete --> RequeteVisual

    -- Branche 1 : Chat RAG & Cartes Officielles Annuaire --
    state "Traitement Annuaire RAG (Zvec + SQL)" as AgentRAG {
        [*] --> ExtractEntities : Extraction NER (Gouvernorats, Stations, Années, Mois)
        ExtractEntities --> CheckRAGMode : RAG Activé ?
        
        state CheckRAGMode {
            state "RAG Activé" as RAGOn
            state "RAG Désactivé" as RAGOff
            
            RAGOn --> VectorSearch : Requête sémantique Zvec (961 passages)
            RAGOn --> SQLQuery : Interrogation directe PostgreSQL (données mm exactes)
            RAGOff --> DirectLLM : Prompt direct au Modèle LLM
        }

        VectorSearch --> LLMVisualDecision : LLM Provider évalue le Catalogue d'Images
        SQLQuery --> LLMVisualDecision
        
        LLMVisualDecision --> ImageExistante : Image Officielle Annuaire Existe ?
        
        state ImageExistante {
            [*] --> ReturnStaticImg : Récupération image (ex: carte_annuelle.png)
        }
    }

    RequeteVisual --> AgentRAG : Mode Chat / Annuaire RAG
    ImageExistante --> FormatterResponse : Image Annuaire trouvée

    -- Branche 2 : Génération Dynamique de Code SIG (Orchestrateur Multi-Agents) --
    state "Orchestrateur Multi-Agents (Génération Dynamique SIG)" as OrchestratorFlow {
        [*] --> ClassifyIntent : Classification d'Intention par LLM (analysis, mono, single_gouv...)
        ClassifyIntent --> SQLAgent : SQLGeneratorAgent traduit en PostgreSQL/PostGIS
        SQLAgent --> DataAudit : DataAuditAgent valide les données et le nombre de stations
        
        state DataAudit {
            [*] --> CheckAudit : Audit Réussi (>0 stations) ?
            CheckAudit --> SIGGen : Oui -> Envoi des métadonnées à SIGGeneratorAgent
            CheckAudit --> FailAudit : Non -> Retour Erreur Données Insuffisantes
        }

        SIGGen --> RAGCodeSnippet : Injection des Snippets Zvec (cKDTree, GeoPandas, Matplotlib)
        RAGCodeSnippet --> LLMCodeGen : Appel LLM Fine-Tuné (Colab / Provider) -> Génération Code Python
        LLMCodeGen --> SandboxExec : Exécution isolée dans SandboxManager (Subprocess)

        state SandboxExec {
            [*] --> ExecCheck : Code retour 0 (Succès) ?
            ExecCheck --> OutputImg : Oui -> Script génère output_isohyete.png / output_table.html
            ExecCheck --> QualityAgent : Non (Erreur/Exception) -> QualityVerificationAgent
        }

        state QualityAgent {
            [*] --> RetryLoop : Injection du Traceback exact + Prompt d'Auto-Correction LLM
            RetryLoop --> SandboxExec : Tentative de Réparation (Max 3 essais)
        }
    }

    ImageExistante --> OrchestratorFlow : Image Non Trouvée (Passage au mode Dynamique)
    RequeteVisual --> OrchestratorFlow : Demande Directe de Carte SIG Sur-Mesure

    -- Branche 3 : Synthèse & Rendu Final --
    OutputImg --> FormatterResponse : Image Dynamique générée
    ReturnStaticImg --> FormatterResponse

    state FormatterResponse {
        [*] --> LLMSummary : Le LLM rédige un résumé exécutif métier (2-3 puces, sans lister les stations)
        LLMSummary --> BuildJSON : Assemblage JSON (Image URL, Code Python, Traces Agents)
    }

    FormatterResponse --> [*] : Affichage sur l'Interface Web CartaGen (Rendu, Code & Traces)
```

---

## 📑 Description Détayée des Étapes d'Activité

### 1. Reception et Analyse de la Requête
- **L'utilisateur** saisit sa question dans le Chat Annuaire ou demande la génération d'une carte pluviométrique.
- **Le système** analyse si l'option **RAG** est activée et identifie le provider LLM sélectionné (`colab`, `groq`, `openai`...).

### 2. Branche RAG Annuaire (Images & Textes Officiels)
- **Extraction NER** : Détection des entités (ex: gouvernorat de *Bizerte*, année *2020*, mois d'*Avril*).
- **Recherche Zvec & SQL** : Extraction simultanée des passages textuels pertinents depuis Zvec Store et des chiffres de pluviométrie exacts depuis la base PostgreSQL (`pluies_148`).
- **Décision Visuelle LLM** : Le modèle LLM compare la demande avec le catalogue officiel d'annuaire. S'il s'agit d'une figure type (ex: `carte_annuelle.png`), l'image est retournée directement sans générer de code.

### 3. Branche Orchestrateur Multi-Agents (Génération Dynamique SIG)
Si la demande nécessite une carte inédite ou si l'image n'existe pas en annuaire :
1. **`SQLGeneratorAgent`** : Traduit la demande en requête PostgreSQL/PostGIS valide.
2. **`DataAuditAgent`** : Vérifie l'existence et la validité des stations météo.
3. **`SIGGeneratorAgent`** : Reçoit les snippets de code SIG depuis Zvec (IDW cKDTree, GeoPandas, Matplotlib) et sollicite le LLM fine-tuné pour produire un script Python autonome.
4. **`SandboxManager`** : Exécute le script Python dans un processus sécurisé et produit la carte `output_isohyete.png`.
5. **`QualityVerificationAgent`** : En cas d'erreur de syntaxe ou d’exécution, intercepte le traceback et pilote la boucle d'auto-correction par le LLM (jusqu'à 3 tentatives).

### 4. Synthèse et Affichage Web
- Le LLM rédige une **courte synthèse métier (2-3 puces)** résumant les cumuls max/min.
- L'interface Web CartaGen affiche le rendu visuel, le code source Python généré et l'historique complet de la communication inter-agents dans l'onglet **Traces Agents**.

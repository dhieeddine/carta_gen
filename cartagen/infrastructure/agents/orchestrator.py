# -*- coding: utf-8 -*-

import os
import time
from datetime import datetime
from typing import Optional
from cartagen.domain.models.map_request import MapRequest, GeneratedMap, ExecutionResult
from cartagen.infrastructure.database.postgres_connection import PostgresConnectionManager
from cartagen.infrastructure.sandbox.sandbox_manager import SandboxManager
from cartagen.infrastructure.agents.sql_generator_agent import SQLGeneratorAgent
from cartagen.infrastructure.agents.sig_generator_agent import SIGGeneratorAgent
from cartagen.infrastructure.database.vector_manager import VectorManager

from cartagen.infrastructure.providers.provider_manager import ProviderManager

class CartaGenOrchestrator:
    """Orchestrateur central responsable de la coordination du workflow multi-agents."""

    def __init__(self, database_url: str, hf_token: str, shapefiles_dir: str, workspace_root: str):
        self.db_manager = PostgresConnectionManager(database_url)
        self.sandbox = SandboxManager(workspace_root, database_url)
        self.shapefiles_dir = shapefiles_dir
        
        # Initialisation de Zvec Vector DB & Provider Manager
        self.vector_manager = VectorManager(workspace_root)
        self.vector_manager.load_collections()
        self.provider_manager = ProviderManager(workspace_root)
        
        # Initialisation des Agents
        self.sql_agent = SQLGeneratorAgent(
            gouv_col="lib_fr",
            reg_col="libelle",
            provider_manager=self.provider_manager
        )
        self.sig_agent = SIGGeneratorAgent(
            hf_token, 
            self.db_manager, 
            vector_manager=self.vector_manager,
            provider_manager=self.provider_manager
        )

    def process_request(self, request: MapRequest, llm_provider: Optional[str] = None) -> GeneratedMap:
        """Exécute le cycle complet de traitement multi-agents.
        
        Args:
            request: La requête de carte à traiter.
            llm_provider: ID du provider LLM à utiliser (ex: 'kaggle', 'openrouter', 'groq').
                          Si None, utilise LLM_PROVIDER depuis .env.
        """
        # ── Résolution du provider actif ──────────────────────────────────────────
        # Recharger .env pour capturer les modifications en cours de session
        from dotenv import load_dotenv
        import os as _os
        load_dotenv(dotenv_path=_os.path.join(self.sandbox.workspace_root, ".env"), override=True)
        
        # 1) Provider explicite du frontend (payload), 2) fallback .env, 3) dernier recours openrouter
        env_provider = _os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
        active_provider = llm_provider.lower().strip() if llm_provider else env_provider

        if self.provider_manager and active_provider in self.provider_manager.providers:
            pinfo = self.provider_manager.providers[active_provider]
            provider = pinfo.get("name", active_provider).upper()
            model_name = pinfo.get("model", "VisCoder2-7B")
        else:
            provider = active_provider.upper()
            if active_provider == "groq":
                model_name = self.sig_agent.groq_model
            elif active_provider == "openai":
                model_name = self.sig_agent.openai_model
            elif active_provider == "openrouter":
                model_name = self.sig_agent.openrouter_model
            elif active_provider == "ollama":
                model_name = self.sig_agent.ollama_model
            else:
                model_name = "VisCoder2-7B (Local)"

        print("="*80)
        print(f"[Orchestrator] Démarrage du traitement de la requête : '{request.prompt}'")
        print(f"[Orchestrator] Configuration active : LLM Provider = {provider} | Modèle = {model_name}")
        print("="*80)
        
        # Recherche sémantique dans Zvec (RAG)
        vector_context = {}
        try:
            print("[Orchestrator -> Zvec DB] Interrogation de l'index vectoriel sémantique...")
            stations = self.vector_manager.query_stations_by_text(request.prompt, topk=5)
            schemas = self.vector_manager.query_schemas_by_text(request.prompt, topk=2)
            vector_context = {"stations": stations, "schemas": schemas}
            if stations:
                print(f"[Zvec DB -> Orchestrator] Stations similaires trouvées : {[s['nom'] for s in stations]}")
            if schemas:
                print(f"[Zvec DB -> Orchestrator] Schémas de tables recommandés : {[s['table_name'] for s in schemas]}")
        except Exception as e:
            print(f"[Orchestrator] Erreur de recherche Zvec : {e}")

        # 1. Génération de la requête SQL d'extraction
        print(f"[Orchestrator -> SQL Agent] Transmission de la requête utilisateur '{request.prompt}' | Provider: {active_provider}")
        self.sql_agent.llm_provider = active_provider
        sql_query, target_col = self.sql_agent.generate_query(request.prompt, vector_context)
        prompt_type = self.sig_agent.detect_prompt_type(request.prompt)
        print(f"[SQL Agent -> Orchestrator] Requête SQL générée :\n---\n{sql_query}\n---")
        print(f"[SQL Agent -> Orchestrator] Colonne cible : '{target_col}' | Type de prompt : '{prompt_type}'")
        
        # 2. Génération initiale du code Python SIG
        print(f"[Orchestrator -> SIG Agent] Appel de la génération de code Python. Provider: {active_provider} | Modèle: {model_name}...")
        self.sig_agent.llm_provider = active_provider
        code = self.sig_agent.generate_code(request.prompt, sql_query, vector_context)
        
        # Injection de la requête SQL réelle dans le code généré
        # Échapper les symboles '%' isolés en '%%' pour éviter que psycopg2 ne les interprète comme des marqueurs de paramètres
        import re
        escaped_sql_query = re.sub(r'(?<!%)%(?!%)', '%%', sql_query)
        code = code.replace("[requete_sql]", escaped_sql_query)
        
        # Gestion des remplacements des squelettes géographiques
        code = self._customize_skeleton_replacements(code, request.prompt, target_col)
        print(f"[SIG Agent -> Orchestrator] Code Python initial généré avec succès ({len(code)} caractères).")
        
        # 3. Exécution dans la Sandbox
        print(f"[Orchestrator -> Sandbox] Lancement de l'exécution isolée du script Python...")
        exec_res = self.sandbox.execute(code, self.shapefiles_dir)
        print(f"[Sandbox -> Orchestrator] Exécution terminée. Statut de succès = {exec_res.success}")
        if not exec_res.success:
            print(f"[Sandbox -> Orchestrator] Message d'erreur : {exec_res.error_message}")
        
        # 4. Cycle d'auto-correction en boucle fermée (Refinement Loop avec injection RAG)
        if not exec_res.success:
            print(f"[Orchestrator -> Quality Agent] Échec détecté dans la Sandbox. Lancement de la boucle d'auto-correction...")
            for attempt in range(1, 3):
                print(f"[Quality Agent -> SIG Agent] Tentative de correction {attempt}/2 via {model_name}...")
                code = self.sig_agent.generate_correction(code, exec_res.error_message, vector_context=vector_context, prompt=request.prompt)
                
                # Ré-exécution
                print(f"[Orchestrator -> Sandbox] Ré-exécution du code corrigé...")
                exec_res = self.sandbox.execute(code, self.shapefiles_dir)
                print(f"[Sandbox -> Orchestrator] Exécution correction terminée. Statut = {exec_res.success}")
                if exec_res.success:
                    print("[Quality Agent -> Orchestrator] Auto-correction réussie avec succès !")
                    break
                else:
                    print(f"[Quality Agent -> Orchestrator] Échec de la tentative de correction : {exec_res.error_message}")

        # 5. Construction de la carte générée finale
        print("="*80)
        print(f"[Orchestrator] Traitement terminé. Résultat global = {'SUCCÈS' if exec_res.success else 'ÉCHEC'}")
        print("="*80)
        
        agent_traces = {
            "sql_agent": {
                "system_prompt": getattr(self.sql_agent, "last_system_prompt", ""),
                "user_prompt": getattr(self.sql_agent, "last_user_prompt", ""),
                "response": getattr(self.sql_agent, "last_response", "")
            },
            "sig_agent": {
                "system_prompt": getattr(self.sig_agent, "last_system_prompt", ""),
                "user_prompt": getattr(self.sig_agent, "last_user_prompt", ""),
                "response": getattr(self.sig_agent, "last_response", "")
            },
            "quality_agent": {
                "system_prompt": getattr(self.sig_agent, "last_correction_system_prompt", ""),
                "user_prompt": getattr(self.sig_agent, "last_correction_user_prompt", ""),
                "response": getattr(self.sig_agent, "last_correction_response", "")
            }
        }
        
        return GeneratedMap(
            request_id=request.request_id,
            prompt=request.prompt,
            prompt_type=prompt_type,
            python_code=code,
            sql_query=sql_query,
            image_url=exec_res.output_image_path,
            created_at=datetime.now(),
            execution_details=exec_res,
            table_html=exec_res.output_table_html,
            agent_traces=agent_traces
        )

    def _customize_skeleton_replacements(self, code: str, prompt: str, target_col: str) -> str:
        """Adapte et personnalise les marqueurs génériques des squelettes."""
        import re
        low = prompt.lower()
        
        # Remplacement de la colonne cible
        code = code.replace("[colonne_cible]", target_col)
        
        # Remplacement du titre de la carte
        code = code.replace("[titre_carte]", prompt)
        code = code.replace("[titre_de_la_carte]", prompt)

        # Extraction des noms géographiques spécifiques
        # Gouvernorat
        gouv_match = re.search(r"gouvernorat de ([\w\s\-]+)", low)
        if not gouv_match:
            gouv_match = re.search(r"gouvernorat d'([\w\s\-]+)", low)
        if gouv_match:
            gouv_name = gouv_match.group(1).strip().capitalize()
            code = code.replace("[NOM_DU_GOUVERNORAT]", gouv_name)
            
        # Comparaison de gouvernorats
        comp_match = re.findall(r"(?:de|à|entre) (tunis|sfax|sousse|bizerte|beja|jendouba|kef|siliana|kairouan|kasserine|sidi bouzid|gabes|gafsa|tozeur|kebili|mednine|tataouine|nabeul|zaghouan|mahdia|monastir|ariana|ben arous|manouba)", low)
        if len(comp_match) >= 2:
            code = code.replace("[GOUVERNORAT_1]", comp_match[0].strip().capitalize())
            code = code.replace("[GOUVERNORAT_2]", comp_match[1].strip().capitalize())

        # Région Hydrographique
        reg_match = re.search(r"région ([\w\s\-]+)", low)
        if not reg_match:
            reg_match = re.search(r"region ([\w\s\-]+)", low)
        if reg_match:
            reg_name = reg_match.group(1).replace("hydrographique", "").strip()
            # Supprimer les préfixes de liaison (de, du, de la, d')
            for prefix in ['de la ', 'de ', 'du ', "d'"]:
                if reg_name.lower().startswith(prefix):
                    reg_name = reg_name[len(prefix):]
                    break
            reg_name = reg_name.strip().capitalize()
            code = code.replace("[NOM_DE_LA_REGION]", reg_name)

        return code

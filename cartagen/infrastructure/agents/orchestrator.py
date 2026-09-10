# -*- coding: utf-8 -*-

import os
import time
import re
from datetime import datetime
from typing import Optional, Dict, Any

from cartagen.domain.models.map_request import MapRequest, GeneratedMap, ExecutionResult
from cartagen.domain.models.agent_message_bus import AgentMessageBus, AgentMessage
from cartagen.infrastructure.database.postgres_connection import PostgresConnectionManager
from cartagen.infrastructure.sandbox.sandbox_manager import SandboxManager
from cartagen.infrastructure.agents.sql_generator_agent import SQLGeneratorAgent
from cartagen.infrastructure.agents.sig_generator_agent import SIGGeneratorAgent
from cartagen.infrastructure.agents.data_audit_agent import DataAuditAgent
from cartagen.infrastructure.database.vector_manager import VectorManager
from cartagen.infrastructure.providers.provider_manager import ProviderManager
from cartagen.infrastructure.logging.dataset_collector import DatasetCollector


class CartaGenOrchestrator:
    """Orchestrateur central délibératif gérant la coopération multi-agents autonome."""

    def __init__(self, database_url: str, hf_token: str, shapefiles_dir: str, workspace_root: str):
        self.database_url = database_url
        self.db_manager = PostgresConnectionManager(database_url)
        self.sandbox = SandboxManager(workspace_root, database_url)
        self.shapefiles_dir = shapefiles_dir
        
        # Initialisation du Collecteur pour Ré-entraînement LoRA
        self.dataset_collector = DatasetCollector(workspace_root)
        
        # Initialisation de Zvec Vector DB & Provider Manager
        self.vector_manager = VectorManager(workspace_root)
        self.vector_manager.load_collections()
        self.provider_manager = ProviderManager(workspace_root)
        
        # Initialisation des Agents Spécialisés
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
        self.audit_agent = DataAuditAgent(database_url)
        self.message_bus = AgentMessageBus()

    def process_request(self, request: MapRequest, llm_provider: Optional[str] = None) -> GeneratedMap:
        """Exécute le cycle coopératif délibératif multi-agents."""
        self.message_bus.clear()
        
        from dotenv import load_dotenv
        import os as _os
        load_dotenv(dotenv_path=_os.path.join(self.sandbox.workspace_root, ".env"), override=True)
        
        env_provider = _os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
        active_provider = llm_provider.lower().strip() if llm_provider else env_provider

        # Log de démarrage sur le Bus
        self.message_bus.publish(AgentMessage(
            sender="Orchestrator",
            receiver="System",
            action="INITIALIZE_WORKFLOW",
            payload={"prompt": request.prompt, "provider": active_provider},
            status="INFO",
            description=f"Démarrage du traitement coopératif pour : '{request.prompt}'"
        ))

        # ── 1. Intent & Zvec Context (Uniquement si RAG est ACTIVÉ) ────────────────
        vector_context = {}
        if getattr(request, "use_rag", True):
            try:
                stations = self.vector_manager.query_stations_by_text(request.prompt, topk=5)
                schemas = self.vector_manager.query_schemas_by_text(request.prompt, topk=2)
                vector_context = {"stations": stations, "schemas": schemas}
                self.message_bus.publish(AgentMessage(
                    sender="ZvecVectorAgent",
                    receiver="Orchestrator",
                    action="RETRIEVE_CONTEXT",
                    payload={"stations_count": len(stations), "schemas_count": len(schemas)},
                    status="SUCCESS",
                    description=f"Contextes vectoriels extraits : {len(stations)} stations, {len(schemas)} schémas."
                ))
            except Exception as e:
                print(f"[Orchestrator] Avertissement Zvec : {e}")
        else:
            self.message_bus.publish(AgentMessage(
                sender="ZvecVectorAgent",
                receiver="Orchestrator",
                action="RETRIEVE_CONTEXT",
                payload={"stations_count": 0, "schemas_count": 0},
                status="SUCCESS",
                description="Mode Pure LLM Direct actif (RAG désactivé — Aucun chargement d'embeddings)."
            ))

        # ── 2. Generation SQL Agent ───────────────────────────────────────────
        self.sql_agent.llm_provider = active_provider
        sql_query, target_col = self.sql_agent.generate_query(request.prompt, vector_context)
        prompt_type = self.sig_agent.detect_prompt_type(request.prompt)

        self.message_bus.publish(AgentMessage(
            sender="SQLGeneratorAgent",
            receiver="DataAuditAgent",
            action="GENERATE_SQL",
            payload={"sql_query": sql_query, "target_col": target_col},
            status="SUCCESS",
            description=f"Requête SQL générée. Colonne cible : '{target_col}'"
        ))

        # ── 3. Data Audit Agent (Contrôle Qualité Données) ─────────────────────
        is_valid, audit_msg, audit_df = self.audit_agent.audit_sql_query(sql_query, target_col)
        
        self.message_bus.publish(AgentMessage(
            sender="DataAuditAgent",
            receiver="SIGGeneratorAgent",
            action="AUDIT_DATA",
            payload={"valid": is_valid, "report": self.audit_agent.last_audit_report},
            status="SUCCESS" if is_valid else "WARNING",
            description=audit_msg
        ))

        # ── 4. Generation SIG Python Agent ────────────────────────────────────
        self.sig_agent.llm_provider = active_provider
        code = self.sig_agent.generate_code(request.prompt, sql_query, vector_context)
        
        escaped_sql_query = re.sub(r'(?<!%)%(?!%)', '%%', sql_query)
        code = code.replace("[requete_sql]", escaped_sql_query)
        code = self._customize_skeleton_replacements(code, request.prompt, target_col)

        self.message_bus.publish(AgentMessage(
            sender="SIGGeneratorAgent",
            receiver="SandboxManager",
            action="GENERATE_PYTHON_CODE",
            payload={"code_length": len(code)},
            status="SUCCESS",
            description=f"Code Python SIG généré ({len(code)} caractères)."
        ))

        # ── 5. Execution Sandbox & Quality Verification Agent ──────────────────
        exec_res = self.sandbox.execute(code, self.shapefiles_dir)

        if exec_res.success:
            self.message_bus.publish(AgentMessage(
                sender="QualityVerificationAgent",
                receiver="Orchestrator",
                action="VERIFY_EXECUTION",
                payload={"execution_time": exec_res.execution_time},
                status="SUCCESS",
                description=f"Exécution Sandbox réussie en {exec_res.execution_time:.2f}s."
            ))
            # Collecte de l'exemple réussi dans le dataset
            self.dataset_collector.record_successful_pair(
                prompt=request.prompt,
                sql_query=sql_query,
                python_code=code,
                provider=active_provider,
                was_corrected=False
            )
        else:
            original_err = exec_res.error_message
            self.message_bus.publish(AgentMessage(
                sender="QualityVerificationAgent",
                receiver="SIGGeneratorAgent",
                action="DETECT_FAILURE",
                payload={"error": exec_res.error_message},
                status="ERROR",
                description=f"Erreur détectée : {exec_res.error_message}. Lancement de la boucle de correction."
            ))
            
            # Boucle d'auto-correction délibérative (Quality Agent ⇄ SIG Agent)
            for attempt in range(1, 3):
                code = self.sig_agent.generate_correction(code, exec_res.error_message, vector_context=vector_context, prompt=request.prompt)
                exec_res = self.sandbox.execute(code, self.shapefiles_dir)
                
                if exec_res.success:
                    self.message_bus.publish(AgentMessage(
                        sender="QualityVerificationAgent",
                        receiver="Orchestrator",
                        action="AUTO_CORRECTION_SUCCESS",
                        payload={"attempt": attempt},
                        status="SUCCESS",
                        description=f"Auto-correction réussie à la tentative {attempt} !"
                    ))
                    # Collecte de l'exemple corrigé avec succès dans le dataset
                    self.dataset_collector.record_successful_pair(
                        prompt=request.prompt,
                        sql_query=sql_query,
                        python_code=code,
                        provider=active_provider,
                        was_corrected=True,
                        original_error=original_err
                    )
                    break

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
            "data_audit_agent": self.audit_agent.last_audit_report,
            "message_bus": self.message_bus.get_traces()
        }

        # Formater l'URL web relative pour l'API et le frontend
        web_image_url = None
        if exec_res.output_image_path:
            filename = os.path.basename(exec_res.output_image_path)
            web_image_url = f"/api/v1/maps/image/{filename}"

        return GeneratedMap(
            request_id=request.request_id,
            prompt=request.prompt,
            prompt_type=prompt_type,
            python_code=code,
            sql_query=sql_query,
            image_url=web_image_url,
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

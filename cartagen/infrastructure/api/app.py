# -*- coding: utf-8 -*-

import os
import sys
import uuid
import subprocess
import unicodedata
import re
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

from cartagen.domain.models.map_request import MapRequest
from cartagen.infrastructure.agents.orchestrator import CartaGenOrchestrator
from cartagen.infrastructure.database.mdb_ingest import MdbIngestionService
from cartagen.infrastructure.database.shapefile_ingest import ShapefileIngestionService
from cartagen.infrastructure.database.annuaire_indexer import AnnuaireIndexer
from cartagen.infrastructure.agents.annuaire_rag_agent import AnnuaireRAGAgent

# Configuration globale via variables d'environnement et Pydantic BaseSettings
from dotenv import load_dotenv
load_dotenv()
from cartagen.infrastructure.config import get_settings

settings = get_settings()
DATABASE_URL = settings.database_url
HF_TOKEN = settings.hf_token
current_dir = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKSPACE_ROOT = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
DEFAULT_SHAPEFILES_DIR = os.path.abspath(os.path.join(DEFAULT_WORKSPACE_ROOT, 'data', 'raw'))

SHAPEFILES_DIR = os.getenv("SHAPEFILES_DIR", DEFAULT_SHAPEFILES_DIR)
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", DEFAULT_WORKSPACE_ROOT)

mdb_service = MdbIngestionService(DATABASE_URL)
shapefile_service = ShapefileIngestionService(DATABASE_URL, SHAPEFILES_DIR)

app = FastAPI(
    title="CartaGen API — Système Multi-Agents DGRE",
    description="API HTTP permettant la génération d'isohyètes à la demande à partir de PostgreSQL.",
    version="1.0.0"
)

# Configuration CORS configurable via .env pour la sécurité en production
ALLOWED_ORIGINS = settings.allowed_origins.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Initialisation de l'orchestrateur
orchestrator = CartaGenOrchestrator(
    database_url=DATABASE_URL,
    hf_token=HF_TOKEN,
    shapefiles_dir=SHAPEFILES_DIR,
    workspace_root=WORKSPACE_ROOT
)

# Initialisation des services Annuaire RAG
annuaire_indexer = AnnuaireIndexer(
    database_url=DATABASE_URL,
    vector_manager=orchestrator.vector_manager
)
annuaire_rag_agent = AnnuaireRAGAgent(
    database_url=DATABASE_URL,
    vector_manager=orchestrator.vector_manager,
    provider_manager=orchestrator.provider_manager,
    orchestrator=orchestrator
)

# Monter le répertoire des fichiers statiques pour le frontend
app.mount("/static", StaticFiles(directory=os.path.join(WORKSPACE_ROOT, "cartagen", "infrastructure", "api", "static")), name="static")

# Registre en mémoire pour suivre l'état des requêtes
task_registry: Dict[str, Dict[str, Any]] = {}

class MapPromptPayload(BaseModel):
    prompt: str
    user_id: Optional[str] = None
    llm_provider: Optional[str] = None   # None = lire LLM_PROVIDER depuis .env au moment de l'exécution
    custom_specifications: Optional[Dict[str, Any]] = None
    use_rag: Optional[bool] = True

class ProviderConfigPayload(BaseModel):
    id: Optional[str] = None
    name: str
    exec_type: str  # api_key, colab, kaggle, ollama, local
    model: str
    endpoint_url: Optional[str] = ""
    api_key: Optional[str] = ""
    description: Optional[str] = ""

class YearbookPayload(BaseModel):
    year: int
    gouv: str

class AnnuaireChatPayload(BaseModel):
    question: str
    llm_provider: Optional[str] = None
    use_rag: Optional[bool] = True

def normalize_string(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', errors='ignore').decode('utf-8')
    s = re.sub(r'[^a-zA-Z0-9]', '_', s)
    s = re.sub(r'_+', '_', s)
    return s.lower().strip('_')

def run_async_yearbook_generation(request_id: str, year: int, gouv: str):
    task_registry[request_id]["status"] = "processing"
    try:
        sandbox_dir = os.path.join(WORKSPACE_ROOT, "sandbox_runs")
        os.makedirs(sandbox_dir, exist_ok=True)
        
        pdf_filename = f"annuaire_{normalize_string(gouv)}_{year}.pdf"
        pdf_path = os.path.join(sandbox_dir, pdf_filename)
        
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            task_registry[request_id].update({
                "status": "completed",
                "pdf_url": f"/api/v1/yearbook/download/{pdf_filename}",
                "logs": "L'annuaire a été récupéré depuis le cache (déjà généré précédemment)."
            })
            return
        
        script_path = os.path.join(WORKSPACE_ROOT, "generer_annuaire_database.py")
        cmd = [
            sys.executable,
            script_path,
            "--year", str(year),
            "--gouv", gouv,
            "--output", pdf_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        
        # Exigence : Vérifier d'abord si le fichier PDF a été généré et est valide, même en cas de warning/erreur pdflatex
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            task_registry[request_id].update({
                "status": "completed",
                "pdf_url": f"/api/v1/yearbook/download/{pdf_filename}",
                "logs": result.stdout
            })
        else:
            task_registry[request_id].update({
                "status": "failed",
                "error": result.stderr or result.stdout or "La compilation a échoué et aucun fichier PDF n'a été produit."
            })
    except Exception as e:
        task_registry[request_id].update({
            "status": "failed",
            "error": f"Exception système inattendue : {str(e)}"
        })

def run_async_generation(request: MapRequest, selected_provider: Optional[str] = None):
    """Fonction exécutée en tâche de fond pour ne pas bloquer l'appel API HTTP."""
    task_id = request.request_id
    task_registry[task_id]["status"] = "processing"
    
    # Recharger .env à chaque exécution pour refléter les modifications en cours de session
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(WORKSPACE_ROOT, ".env"), override=True)
    
    # Le provider vient : 1) du choix explicite frontend, 2) sinon du .env (LLM_PROVIDER)
    env_provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
    active_provider = selected_provider.lower().strip() if selected_provider else env_provider
    print(f"[API] run_async_generation démarrée | Provider frontend: '{selected_provider}' | .env LLM_PROVIDER: '{env_provider}' | Provider actif: '{active_provider}'")
    
    try:
        # Passer le provider explicitement à process_request() — 
        # pas de mutation de l'état global des agents (thread-safe)
        generated_map = orchestrator.process_request(request, llm_provider=active_provider)
        
        if generated_map.execution_details.success:
            task_registry[task_id].update({
                "status": "completed",
                "image_path": generated_map.image_url,
                "code": generated_map.python_code,
                "sql": generated_map.sql_query,
                "execution_time": generated_map.execution_details.execution_time,
                "table_html": generated_map.table_html,
                "agent_traces": generated_map.agent_traces
            })
        else:
            task_registry[task_id].update({
                "status": "failed",
                "error": generated_map.execution_details.error_message,
                "code": generated_map.python_code,
                "agent_traces": generated_map.agent_traces
            })
    except Exception as e:
        task_registry[task_id].update({
            "status": "failed",
            "error": f"Exception système inattendue : {str(e)}"
        })

@app.post("/api/v1/maps/generate", status_code=202)
async def generate_map(payload: MapPromptPayload, background_tasks: BackgroundTasks):
    """Soumet un nouveau prompt pour générer une carte d'isohyètes."""
    request_id = str(uuid.uuid4())
    
    map_request = MapRequest(
        prompt=payload.prompt,
        request_id=request_id,
        created_at=datetime.now(),
        user_id=payload.user_id,
        custom_specifications=payload.custom_specifications,
        use_rag=payload.use_rag if getattr(payload, 'use_rag', None) is not None else True
    )
    
    # Enregistrer la tâche dans le registre
    task_registry[request_id] = {
        "status": "queued",
        "prompt": payload.prompt,
        "llm_provider": payload.llm_provider,
        "created_at": map_request.created_at.isoformat()
    }
    
    # Lancer le traitement asynchrone en passant le provider choisi
    background_tasks.add_task(run_async_generation, map_request, payload.llm_provider)
    
    return {
        "message": "Demande de carte reçue et en cours de traitement.",
        "request_id": request_id,
        "status": "queued",
        "llm_provider": payload.llm_provider
    }

@app.get("/api/v1/providers")
async def get_providers():
    """Récupère la liste dynamique des providers LLM configurés."""
    return {
        "providers": orchestrator.provider_manager.get_providers_list()
    }

@app.post("/api/v1/providers/add")
async def add_provider(payload: ProviderConfigPayload):
    """Ajoute ou met à jour dynamiquement un provider LLM (API, Colab, Kaggle, Local)."""
    try:
        config = orchestrator.provider_manager.add_or_update_provider(payload.dict())
        return {
            "message": f"Provider '{config['name']}' ajouté et configuré avec succès !",
            "provider": config
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/maps/status/{request_id}")
async def get_map_status(request_id: str):
    """Récupère l'état d'avancement et les résultats d'une demande."""
    if request_id not in task_registry:
        raise HTTPException(status_code=404, detail="Requête introuvable.")
    
    task_data = task_registry[request_id]
    
    # Si la tâche est en cours d'exécution, attacher les traces du MessageBus et des Prompts LLM en temps réel
    if task_data.get("status") in ["queued", "processing"]:
        if "agent_traces" not in task_data:
            task_data["agent_traces"] = {}
        task_data["agent_traces"]["message_bus"] = orchestrator.message_bus.get_traces()
        if hasattr(orchestrator.audit_agent, "last_audit_report") and orchestrator.audit_agent.last_audit_report:
            task_data["agent_traces"]["data_audit_agent"] = orchestrator.audit_agent.last_audit_report
        task_data["agent_traces"]["sql_agent"] = {
            "system_prompt": getattr(orchestrator.sql_agent, "last_system_prompt", ""),
            "user_prompt": getattr(orchestrator.sql_agent, "last_user_prompt", ""),
            "response": getattr(orchestrator.sql_agent, "last_response", "")
        }
        task_data["agent_traces"]["sig_agent"] = {
            "system_prompt": getattr(orchestrator.sig_agent, "last_system_prompt", ""),
            "user_prompt": getattr(orchestrator.sig_agent, "last_user_prompt", ""),
            "response": getattr(orchestrator.sig_agent, "last_response", "")
        }
        task_data["agent_traces"]["annuaire_rag_agent"] = {
            "system_prompt": getattr(annuaire_rag_agent, "last_system_prompt", ""),
            "user_prompt": getattr(annuaire_rag_agent, "last_user_prompt", ""),
            "response": getattr(annuaire_rag_agent, "last_response", "")
        }

    # Si terminé, renvoyer l'URL d'accès à l'image plutôt que le chemin disque local
    response = task_data.copy()
    if task_data.get("status") == "completed" and "image_path" in task_data:
        filename = os.path.basename(task_data["image_path"])
        response["image_url"] = f"/api/v1/maps/image/{filename}"
        if "image_path" in response:
            del response["image_path"]
            
    return response

@app.get("/api/v1/maps/image/{filename}")
async def get_map_image(filename: str):
    """Sert l'image de la carte d'isohyètes générée par la Sandbox."""
    safe_filename = os.path.basename(filename)
    sandbox_dir = os.path.abspath(os.path.join(WORKSPACE_ROOT, "sandbox_runs"))
    image_path = os.path.abspath(os.path.join(sandbox_dir, safe_filename))
    
    if not image_path.startswith(sandbox_dir) or not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image de carte non trouvée.")
        
    return FileResponse(image_path, media_type="image/png")

@app.get("/api/v1/annuaire/image/{folder_name}/{filename}")
async def get_annuaire_image(folder_name: str, filename: str):
    """Sert les images de cartes/statistiques générées pour l'annuaire."""
    if not re.match(r"^images_temp_[a-zA-Z0-9_]+$", folder_name):
        raise HTTPException(status_code=400, detail="Nom de dossier invalide.")
        
    safe_filename = os.path.basename(filename)
    base_folder = os.path.abspath(os.path.join(WORKSPACE_ROOT, folder_name))
    image_path = os.path.abspath(os.path.join(base_folder, safe_filename))
    
    if not image_path.startswith(base_folder) or not os.path.exists(image_path):
        fallback_dir = os.path.abspath(os.path.join(WORKSPACE_ROOT, "images_temp"))
        fallback_path = os.path.abspath(os.path.join(fallback_dir, safe_filename))
        if fallback_path.startswith(fallback_dir) and os.path.exists(fallback_path):
            return FileResponse(fallback_path, media_type="image/png")
        raise HTTPException(status_code=404, detail="Image de l'annuaire non trouvée.")
        
    return FileResponse(image_path, media_type="image/png")



@app.post("/api/v1/yearbook/generate", status_code=202)
async def generate_yearbook(payload: YearbookPayload, background_tasks: BackgroundTasks):
    """Soumet une demande de génération de l'annuaire pluviométrique."""
    request_id = str(uuid.uuid4())
    task_registry[request_id] = {
        "status": "queued",
        "type": "yearbook",
        "year": payload.year,
        "gouv": payload.gouv,
        "created_at": datetime.now().isoformat()
    }
    background_tasks.add_task(run_async_yearbook_generation, request_id, payload.year, payload.gouv)
    return {
        "message": "Génération de l'annuaire pluviométrique en cours.",
        "request_id": request_id,
        "status": "queued"
    }

@app.get("/api/v1/yearbook/download/{filename}")
async def download_yearbook(filename: str):
    """Télécharge le fichier PDF généré de l'annuaire."""
    safe_filename = os.path.basename(filename)
    if not safe_filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Format de fichier non autorisé.")
    sandbox_dir = os.path.abspath(os.path.join(WORKSPACE_ROOT, "sandbox_runs"))
    pdf_path = os.path.abspath(os.path.join(sandbox_dir, safe_filename))
    if not pdf_path.startswith(sandbox_dir) or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Annuaire PDF introuvable.")
    return FileResponse(pdf_path, media_type="application/pdf", filename=safe_filename)

@app.post("/api/v1/data/ingest-mdb")
async def ingest_mdb_file(
    file: UploadFile = File(...),
    gouvernorat: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None
):
    """Reçoit un fichier MS Access (.mdb / .accdb) et l'ingère dans PostgreSQL avec auto-détection du gouvernorat."""
    if not (file.filename.endswith(".mdb") or file.filename.endswith(".accdb")):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .mdb ou .accdb sont acceptés.")

    upload_dir = os.path.join(WORKSPACE_ROOT, "sandbox_runs", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    gouv_prefix = normalize_string(gouvernorat) if gouvernorat else "auto"
    saved_path = os.path.join(upload_dir, f"{gouv_prefix}_{file.filename}")
    try:
        with open(saved_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        result = mdb_service.ingest_mdb_file(saved_path, gouvernorat)
        if not result.get("success"):
            err_msg = result.get("error", "Échec de l'ingestion MDB.")
            print(f"[API Ingest MDB] Échec : {err_msg}\n{result.get('traceback', '')}")
            raise HTTPException(status_code=500, detail=err_msg)
            
        # Déclenchement automatique de l'indexation Zvec
        if background_tasks:
            background_tasks.add_task(annuaire_indexer.index)
            print("[API Ingest MDB] Indexation Zvec lancée automatiquement en arrière-plan.")
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[API Ingest MDB] Exception : {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement de l'ingestion : {str(e)}")

@app.post("/api/v1/data/ingest-shapefiles")
async def ingest_shapefiles():
    """Vérifie ou ingère les bases spatiales (Shapefiles) dans PostgreSQL."""
    try:
        result = shapefile_service.ingest_shapefiles()
        if not result.get("success"):
            # Si des erreurs partielles, on peut quand même renvoyer 200 avec le message, ou 500
            pass # We return the result and let the frontend handle the display
        return result
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[API Ingest Shapefiles] Exception : {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'ingestion des shapefiles : {str(e)}")

@app.post("/api/v1/annuaire/index", status_code=202)
async def index_annuaire_data(background_tasks: BackgroundTasks):
    """Indexe (ou réindexe) les données pluviométriques de la BDD dans Zvec."""
    def run_indexation():
        try:
            result = annuaire_indexer.index()
            print(f"[API] Indexation annuaire : {result}")
        except Exception as e:
            print(f"[API] Erreur indexation annuaire : {e}")

    background_tasks.add_task(run_indexation)
    return {
        "message": "Indexation des données pluviométriques lancée en arrière-plan.",
        "status": "indexing"
    }

@app.post("/api/v1/annuaire/chat")
async def chat_annuaire(payload: AnnuaireChatPayload, background_tasks: BackgroundTasks):
    """Répond aux questions sur les annuaires pluviométriques via RAG ou LLM Direct (non-bloquant)."""
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="La question ne peut pas être vide.")
    
    # Créer un ID unique pour suivre la tâche dans le registre
    request_id = str(uuid.uuid4())
    task_registry[request_id] = {
        "status": "processing",
        "question": payload.question,
        "created_at": datetime.now().isoformat()
    }
    
    def run_async_chat():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=os.path.join(WORKSPACE_ROOT, ".env"), override=True)

            env_provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
            active_provider = payload.llm_provider.lower().strip() if payload.llm_provider else env_provider
            use_rag_flag = bool(payload.use_rag) if payload.use_rag is not None else True
            
            result = annuaire_rag_agent.answer(payload.question, llm_provider=active_provider, use_rag=use_rag_flag)
            
            # Normalisation systématique des URLs d'images pour le navigateur
            raw_images = result.get("images", [])
            normalized_images = []
            for img in raw_images:
                if img.startswith("http://") or img.startswith("https://") or img.startswith("/"):
                    normalized_images.append(img)
                else:
                    filename = os.path.basename(img)
                    normalized_images.append(f"/api/v1/maps/image/{filename}")

            task_registry[request_id].update({
                "status": "completed",
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
                "nb_passages": result.get("nb_passages", 0),
                "images": normalized_images,
                "code": result.get("code", ""),
                "table_html": result.get("table_html", None),
                "agent_traces": result.get("agent_traces", {})
            })
        except Exception as e:
            task_registry[request_id].update({
                "status": "failed",
                "error": str(e)
            })

    background_tasks.add_task(run_async_chat)
    
    return {
        "request_id": request_id,
        "status": "processing"
    }

@app.get("/health")
async def health_check():
    """Endpoint simple de supervision de l'API."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/", response_class=HTMLResponse)
async def read_index():
    """Sert la page d'accueil (Dashboard) de CartaGen."""
    index_path = os.path.join(WORKSPACE_ROOT, "cartagen", "infrastructure", "api", "static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

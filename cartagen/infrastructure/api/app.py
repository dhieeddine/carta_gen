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
from cartagen.infrastructure.database.annuaire_indexer import AnnuaireIndexer
from cartagen.infrastructure.agents.annuaire_rag_agent import AnnuaireRAGAgent

# Configuration globale via variables d'environnement
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dgre_db")
HF_TOKEN = os.getenv("HF_TOKEN", "")
SHAPEFILES_DIR = os.getenv("SHAPEFILES_DIR", r"D:\Desktop\stage_dgre\backend\data\raw")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", r"D:\Desktop\stage_dgre\carta_gen")

mdb_service = MdbIngestionService(DATABASE_URL)

app = FastAPI(
    title="CartaGen API — Système Multi-Agents DGRE",
    description="API HTTP permettant la génération d'isohyètes à la demande à partir de PostgreSQL.",
    version="1.0.0"
)

# Configuration CORS pour permettre la connexion du Frontend web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    provider_manager=orchestrator.provider_manager
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
        
        pdf_filename = f"annuaire_{normalize_string(gouv)}_{year}_{request_id}.pdf"
        pdf_path = os.path.join(sandbox_dir, pdf_filename)
        
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
                "table_html": generated_map.table_html
            })
        else:
            task_registry[task_id].update({
                "status": "failed",
                "error": generated_map.execution_details.error_message,
                "code": generated_map.python_code
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
        custom_specifications=payload.custom_specifications
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
    
    # Si terminé, renvoyer l'URL d'accès à l'image plutôt que le chemin disque local
    response = task_data.copy()
    if task_data.get("status") == "completed" and "image_path" in task_data:
        filename = os.path.basename(task_data["image_path"])
        response["image_url"] = f"/api/v1/maps/image/{filename}"
        # Supprimer le chemin d'accès absolu pour la sécurité
        if "image_path" in response:
            del response["image_path"]
            
    return response

@app.get("/api/v1/maps/image/{filename}")
async def get_map_image(filename: str):
    """Sert l'image de la carte d'isohyètes générée par la Sandbox."""
    # Recherche dans le dossier temporaire de la Sandbox
    sandbox_dir = os.path.join(WORKSPACE_ROOT, "sandbox_runs")
    image_path = os.path.join(sandbox_dir, filename)
    
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image de carte non trouvée.")
        
    return FileResponse(image_path, media_type="image/png")

@app.get("/api/v1/annuaire/image/{folder_name}/{filename}")
async def get_annuaire_image(folder_name: str, filename: str):
    """Sert les images de cartes/statistiques générées pour l'annuaire."""
    if not re.match(r"^images_temp_[a-zA-Z0-9_]+$", folder_name):
        raise HTTPException(status_code=400, detail="Nom de dossier invalide.")
        
    image_path = os.path.join(WORKSPACE_ROOT, folder_name, filename)
    
    if not os.path.exists(image_path):
        # Fallback de compatibilité vers images_temp au cas où
        fallback_path = os.path.join(WORKSPACE_ROOT, "images_temp", filename)
        if os.path.exists(fallback_path):
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
    sandbox_dir = os.path.join(WORKSPACE_ROOT, "sandbox_runs")
    pdf_path = os.path.join(sandbox_dir, filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Annuaire PDF introuvable.")
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)

@app.post("/api/v1/data/ingest-mdb")
async def ingest_mdb_file(
    file: UploadFile = File(...),
    gouvernorat: Optional[str] = Form(None)
):
    """Reçoit un fichier MS Access (.mdb / .accdb) et l l'ingère dans PostgreSQL avec auto-détection du gouvernorat."""
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
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[API Ingest MDB] Exception : {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement de l'ingestion : {str(e)}")

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
async def chat_annuaire(payload: AnnuaireChatPayload):
    """Répond aux questions sur les annuaires pluviométriques via RAG (Zvec + SQL + LLM)."""
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="La question ne peut pas être vide.")
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=os.path.join(WORKSPACE_ROOT, ".env"), override=True)

        env_provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
        active_provider = payload.llm_provider.lower().strip() if payload.llm_provider else env_provider

        result = annuaire_rag_agent.answer(payload.question, llm_provider=active_provider)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur du service RAG : {str(e)}")

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

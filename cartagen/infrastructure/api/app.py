# -*- coding: utf-8 -*-

import os
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

from cartagen.domain.models.map_request import MapRequest
from cartagen.infrastructure.agents.orchestrator import CartaGenOrchestrator

# Configuration globale via variables d'environnement
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/yasra")
HF_TOKEN = os.getenv("HF_TOKEN", "")
SHAPEFILES_DIR = os.getenv("SHAPEFILES_DIR", r"D:\Desktop\stage_dgre\backend\data\raw")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", r"D:\Desktop\stage_dgre\carta_gen")

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

# Monter le répertoire des fichiers statiques pour le frontend
app.mount("/static", StaticFiles(directory=os.path.join(WORKSPACE_ROOT, "cartagen", "infrastructure", "api", "static")), name="static")

# Registre en mémoire pour suivre l'état des requêtes
task_registry: Dict[str, Dict[str, Any]] = {}

class MapPromptPayload(BaseModel):
    prompt: str
    user_id: Optional[str] = None
    custom_specifications: Optional[Dict[str, Any]] = None

def run_async_generation(request: MapRequest):
    """Fonction exécutée en tâche de fond pour ne pas bloquer l'appel API HTTP."""
    task_id = request.request_id
    task_registry[task_id]["status"] = "processing"
    
    try:
        generated_map = orchestrator.process_request(request)
        
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
        "created_at": map_request.created_at.isoformat()
    }
    
    # Lancer le traitement asynchrone
    background_tasks.add_task(run_async_generation, map_request)
    
    return {
        "message": "Demande de carte reçue et en cours de traitement.",
        "request_id": request_id,
        "status": "queued"
    }

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

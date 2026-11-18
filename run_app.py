# -*- coding: utf-8 -*-

import os
import uvicorn
from dotenv import load_dotenv

# Charger les variables d'environnement (.env) sans écraser les variables déjà injectées par Docker
saved_db = os.environ.get("DATABASE_URL")
load_dotenv()
if saved_db:
    os.environ["DATABASE_URL"] = saved_db

if __name__ == "__main__":
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/dgre_db"
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    reload_enabled = os.getenv("RELOAD", "true").lower() in ("true", "1", "yes")

    print(f"[CartaGen] Lancement du serveur sur http://{host}:{port} (reload={reload_enabled})")
    
    uvicorn.run(
        "cartagen.infrastructure.api.app:app",
        host=host,
        port=port,
        reload=reload_enabled,
        reload_dirs=["cartagen"] if reload_enabled else None,
        reload_excludes=["*.pyc", "*.log", "sandbox_runs/*", "images_temp/*", "zvec_store/*"] if reload_enabled else None
    )


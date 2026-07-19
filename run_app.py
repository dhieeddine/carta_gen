# -*- coding: utf-8 -*-

import os
import uvicorn
from dotenv import load_dotenv

# Charger les variables d'environnement (.env)
load_dotenv()

if __name__ == "__main__":
    # Définir l'URL de base de données par défaut si absente
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/yasra"
    
    # Démarrer le serveur HTTP asynchrone sur le port 8000
    uvicorn.run(
        "cartagen.infrastructure.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )

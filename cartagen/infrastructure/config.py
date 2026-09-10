# -*- coding: utf-8 -*-
"""Configuration centralisée de CartaGen via Pydantic BaseSettings."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Toutes les variables d'environnement sont validées et centralisées ici."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/dgre_db"

    # Hugging Face
    hf_token: str = ""

    # LLM
    llm_provider: str = "openrouter"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.1-8b-instruct:free"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ollama_colab_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Application
    workspace_root: str = "."
    shapefiles_dir: str = "./data/raw"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    """Retourne l'instance singleton mise en cache des paramètres."""
    return Settings()

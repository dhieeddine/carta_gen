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
    ollama_colab_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    def model_post_init(self, __context):
        in_docker = os.getenv("IN_DOCKER", "false").lower() in ("true", "1") or os.path.exists("/.dockerenv")
        if in_docker and self.ollama_colab_url:
            self.ollama_colab_url = self.ollama_colab_url.replace("://localhost", "://host.docker.internal").replace("://127.0.0.1", "://host.docker.internal")

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

# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/logging/logger.py
=========================================
Configuration centralisée du logging pour CartaGen.
Supporte :
- Structured JSON Logging (conforme observabilité Cloud-Native / ELK / Loki)
- Correlation ID / Request ID distribué via ContextVars
- Masquage automatique des secrets et clés API (SensitiveDataFilter)
- Rotation des fichiers journaux (5 Mo, 5 archives)
"""

import os
import re
import json
import logging
from logging.handlers import RotatingFileHandler
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Variables de contexte asynchrones pour la traçabilité de bout en bout
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="system")
current_user_ctx: ContextVar[str] = ContextVar("current_user", default="anonymous")


class SensitiveDataFilter(logging.Filter):
    """Filtre de sécurité masquant automatiquement les secrets dans les logs."""

    PATTERNS = [
        (re.compile(r'(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*["\']?([^"\'\s]+)["\']?'), r'\1="***MASKED***"'),
        (re.compile(r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*', re.IGNORECASE), 'Bearer ***MASKED***'),
        (re.compile(r'hf_[a-zA-Z0-9]{30,}', re.IGNORECASE), 'hf_***MASKED***'),
        (re.compile(r'gsk_[a-zA-Z0-9]{30,}', re.IGNORECASE), 'gsk_***MASKED***'),
        (re.compile(r'sk-[a-zA-Z0-9]{30,}', re.IGNORECASE), 'sk-***MASKED***')
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, repl in self.PATTERNS:
                record.msg = pattern.sub(repl, record.msg)
        return True


class JsonFormatter(logging.Formatter):
    """Formateur JSON structuré pour les logs de production."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": correlation_id_ctx.get(),
            "user": current_user_ctx.get(),
            "message": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
            "process": record.process,
            "thread": record.threadName
        }

        # Données contextuelles supplémentaires
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_payload["details"] = record.extra_data

        # Traces d'exception
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, ensure_ascii=False)


def setup_logger(
    name: str = "cartagen",
    level: Optional[str] = None,
    log_dir: Optional[str] = None,
    json_format: bool = True
) -> logging.Logger:
    """Configure et retourne un logger nommé avec rotation et traçabilité contextuelle.

    Args:
        name: Nom du module (ex: 'cartagen.agents.sql')
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR). Par défaut lit LOG_LEVEL du .env.
        log_dir: Répertoire de stockage des logs.
        json_format: Si True, formate les sorties en JSON.

    Returns:
        logging.Logger: Logger configuré.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False

    if logger.handlers:
        return logger  # Déjà configuré

    # Filtre de masquage des secrets
    sec_filter = SensitiveDataFilter()
    logger.addFilter(sec_filter)

    # Formateur
    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [corr=%(correlation_id)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level, logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler (Rotation 5 Mo, 5 archives)
    if log_dir is None:
        log_dir = os.path.join(os.getenv("WORKSPACE_ROOT", "."), "logs")

    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "cartagen.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, level, logging.INFO))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"[Logging] Note : écriture fichier désactivée ({e})")

    return logger

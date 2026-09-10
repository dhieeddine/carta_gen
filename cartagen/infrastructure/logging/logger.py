# -*- coding: utf-8 -*-
"""Configuration centralisée du logging pour CartaGen."""

import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "cartagen", level: str = None) -> logging.Logger:
    """Configure et retourne un logger nommé avec rotation des fichiers.

    Args:
        name: Nom du logger (ex: 'cartagen.agents.sql')
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR). Par défaut, lit LOG_LEVEL du .env.

    Returns:
        logging.Logger: Logger configuré.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # Déjà configuré

    logger.setLevel(getattr(logging, level, logging.INFO))

    # Format standardisé
    fmt = logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level, logging.INFO))
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # File Handler (rotation 5 Mo, 3 backups)
    log_dir = os.path.join(os.getenv("WORKSPACE_ROOT", "."), "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "cartagen.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception:
        pass  # En cas d'impossibilité d'écriture disque

    return logger

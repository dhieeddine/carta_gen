# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/concurrency/pessimistic_lock.py
=======================================================
Gestionnaire de Verrouillage Pessimiste / Mutex Applicatif (Pessimistic Concurrency Control).
Garantit l'exclusion mutuelle stricte sur les traitements par lots lourds
(ex: ingestion d'une base Microsoft Access ou compilation d'un annuaire national).
"""

import threading
import time
from typing import Dict, Optional
from datetime import datetime, timezone
from fastapi import HTTPException, status
from cartagen.infrastructure.logging.logger import setup_logger

logger = setup_logger("cartagen.concurrency.pessimistic")


class JobAlreadyRunningError(Exception):
    """Exception levée lorsqu'un verrou exclusif est déjà détenu."""
    pass


class TaskMutexManager:
    """Gestionnaire de verrous exclusifs en mémoire avec expiration automatique (Timeout/TTL)."""

    def __init__(self):
        self._locks: Dict[str, Dict[str, Any]] = {}
        self._mutex = threading.Lock()

    def acquire_lock(self, task_key: str, owner: str = "system", timeout_seconds: int = 300) -> bool:
        """Tente d'acquérir un verrou exclusif sur task_key."""
        now = time.time()
        with self._mutex:
            # Vérifier si le verrou existe et est encore valide
            if task_key in self._locks:
                lock_info = self._locks[task_key]
                if now < lock_info["expires_at"]:
                    logger.warning(
                        f"[PessimisticLock] Conflit d'accès : la tâche '{task_key}' est déjà verrouillée par '{lock_info['owner']}'."
                    )
                    raise JobAlreadyRunningError(
                        f"La tâche '{task_key}' est déjà en cours d'exécution par '{lock_info['owner']}'. "
                        f"Verrou actif jusqu'à {datetime.fromtimestamp(lock_info['expires_at'], tz=timezone.utc).isoformat()}."
                    )
                else:
                    logger.info(f"[PessimisticLock] Verrou expiré sur '{task_key}', libération automatique.")

            # Acquisition du verrou
            self._locks[task_key] = {
                "owner": owner,
                "acquired_at": now,
                "expires_at": now + timeout_seconds
            }
            logger.info(f"[PessimisticLock] Verrou acquis sur '{task_key}' par '{owner}' (TTL: {timeout_seconds}s).")
            return True

    def release_lock(self, task_key: str, owner: Optional[str] = None) -> bool:
        """Libère un verrou exclusif."""
        with self._mutex:
            if task_key in self._locks:
                del self._locks[task_key]
                logger.info(f"[PessimisticLock] Verrou libéré sur '{task_key}'.")
                return True
            return False

    def is_locked(self, task_key: str) -> bool:
        """Vérifie si une tâche est actuellement verrouillée."""
        now = time.time()
        with self._mutex:
            if task_key in self._locks:
                return now < self._locks[task_key]["expires_at"]
            return False


# Singleton Mutex Manager
task_mutex_manager = TaskMutexManager()

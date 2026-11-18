# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/concurrency/optimistic_lock.py
======================================================
Gestionnaire de Conflits par Verrouillage Optimiste (Optimistic Concurrency Control - OCC).
Empêche l'écrasement silencieux de données par des modifications concurrentes (Lost Update Problem).

Fonctionnement :
- Chaque ressource critique dispose d'un numéro de version incrémental et d'un ETag.
- Lors d'une mise à jour (PUT / PATCH), le client transmet la version attendue (ou l'en-tête If-Match).
- Si la ressource a été modifiée entre-temps par un autre utilisateur, la requête est rejetée avec HTTP 409 Conflict.
- Le conflit est systématiquement consigné dans le registre d'audit pour diagnostic.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from fastapi import HTTPException, status
from cartagen.infrastructure.logging.audit_logger import AuditLogger

audit_logger = AuditLogger()


class OptimisticLockConflictError(Exception):
    """Exception levée lors de la détection d'une divergence de version concurrente."""

    def __init__(self, resource_id: str, current_version: int, expected_version: int):
        self.resource_id = resource_id
        self.current_version = current_version
        self.expected_version = expected_version
        self.message = (
            f"Conflit de concurrence sur la ressource '{resource_id}'. "
            f"Version actuelle du système: {current_version}, version soumise: {expected_version}. "
            "Un autre utilisateur a modifié cet enregistrement. Veuillez actualiser puis réitérer."
        )
        super().__init__(self.message)


class OptimisticLockManager:
    """Gestionnaire central de concurrence optimiste pour configurations et entités métier."""

    def __init__(self):
        # Stockage mémoire pour démonstration et intégration rapide (persistant via DB en prod)
        self._store: Dict[str, Dict[str, Any]] = {}

    def _generate_etag(self, resource_id: str, version: int, data: Dict[str, Any]) -> str:
        payload = f"{resource_id}:{version}:{json.dumps(data, sort_keys=True)}"
        return f'"{hashlib.sha256(payload.encode()).hexdigest()[:16]}"'

    def register_or_get(self, resource_id: str, default_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Récupère une ressource avec sa version et son ETag."""
        if resource_id not in self._store:
            initial_data = default_data or {}
            self._store[resource_id] = {
                "version": 1,
                "data": initial_data,
                "etag": self._generate_etag(resource_id, 1, initial_data),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": "system"
            }
        return self._store[resource_id]

    def update_resource(
        self,
        resource_id: str,
        new_data: Dict[str, Any],
        expected_version: int,
        user: str = "anonymous",
        client_ip: str = "127.0.0.1"
    ) -> Dict[str, Any]:
        """Met à jour une ressource en validant strictement la non-divergence de version."""
        current_record = self.register_or_get(resource_id)
        current_version = current_record["version"]

        # Détection du conflit (Lost Update Detection)
        if expected_version != current_version:
            # Audit de l'incident de concurrence
            audit_logger.log_event(
                action="UPDATE_CONFLICT_REJECTED",
                resource=f"resource:{resource_id}",
                status="REJECTED_409",
                ip_address=client_ip,
                details={
                    "expected_version": expected_version,
                    "current_version": current_version,
                    "reason": "Lost Update Prevention via Optimistic Locking"
                }
            )
            raise OptimisticLockConflictError(
                resource_id=resource_id,
                current_version=current_version,
                expected_version=expected_version
            )

        # Application de la mutation atomique
        previous_data = current_record["data"]
        new_version = current_version + 1
        new_etag = self._generate_etag(resource_id, new_version, new_data)

        updated_record = {
            "version": new_version,
            "data": new_data,
            "etag": new_etag,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user
        }
        self._store[resource_id] = updated_record

        # Audit de la réussite
        audit_logger.log_event(
            action="UPDATE_OCC_SUCCESS",
            resource=f"resource:{resource_id}",
            status="SUCCESS",
            ip_address=client_ip,
            previous_state={"version": current_version, "data": previous_data},
            new_state={"version": new_version, "data": new_data}
        )

        return updated_record


# Instance Singleton du gestionnaire de concurrence optimiste
optimistic_lock_manager = OptimisticLockManager()


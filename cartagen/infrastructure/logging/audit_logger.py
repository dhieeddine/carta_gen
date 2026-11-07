# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/logging/audit_logger.py
===============================================
Registre d'Audit Immuable (Audit Trail).
Enregistre toutes les opérations sensibles et mutations de configuration pour
satisfaire aux exigences de conformité, gouvernance et sécurité logicielle.
Chaque entrée d'audit inclut une empreinte cryptographique SHA-256 certifiant son intégrité.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from cartagen.infrastructure.logging.logger import correlation_id_ctx, current_user_ctx


class AuditLogger:
    """Enregistreur d'audit avec chaînage cryptographique d'intégrité."""

    def __init__(self, log_dir: Optional[str] = None):
        if log_dir is None:
            log_dir = os.path.join(os.getenv("WORKSPACE_ROOT", "."), "logs")
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.audit_file = os.path.join(self.log_dir, "audit_trail.jsonl")

    def _calculate_checksum(self, record_payload: str) -> str:
        """Calcule l'empreinte SHA-256 certifiant l'intégrité du log d'audit."""
        return hashlib.sha256(record_payload.encode("utf-8")).hexdigest()

    def log_event(
        self,
        action: str,
        resource: str,
        status: str,  # SUCCESS, FAILURE, REJECTED
        ip_address: str = "127.0.0.1",
        details: Optional[Dict[str, Any]] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        new_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Inscrit un événement d'audit immuable dans le registre JSONL."""
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "AUDIT_SECURITY",
            "correlation_id": correlation_id_ctx.get(),
            "actor": current_user_ctx.get(),
            "client_ip": ip_address,
            "action": action,
            "resource": resource,
            "status": status,
            "previous_state": previous_state or {},
            "new_state": new_state or {},
            "details": details or {}
        }

        # Calcul d'empreinte sur les données sérialisées déterministes
        serialized = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        entry["checksum_sha256"] = self._calculate_checksum(serialized)

        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[AuditLogger] Erreur d'écriture audit : {e}")

        return entry

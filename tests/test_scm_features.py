# -*- coding: utf-8 -*-
"""
tests/test_scm_features.py
==========================
Suite Complète de Tests Automatisés Validant les 3 Volets du Sujet 10 (SCM) :
- Volet 1 : Journalisation (Logging Contextuel, Structured JSON, Audit Trail SHA-256, Masquage)
- Volet 2 : Gestion des Versions (SemVer 2.0, Métadonnées, Découverte Alembic)
- Volet 3 : Gestion des Conflits (Optimistic Locking Concurrence, Mutex Pessimiste)

Conçu pour une exécution déterministe et ultra-rapide (< 1 seconde).
"""

import os
import json
import unittest
import asyncio
from datetime import datetime

from cartagen.version import __version__, get_version_metadata, VERSION_INFO
from cartagen.infrastructure.logging import (
    setup_logger,
    correlation_id_ctx,
    current_user_ctx,
    AuditLogger,
    SensitiveDataFilter
)
from cartagen.infrastructure.concurrency import (
    OptimisticLockManager,
    OptimisticLockConflictError,
    TaskMutexManager,
    JobAlreadyRunningError
)
from cartagen.infrastructure.database.migrations.migration_manager import DatabaseMigrationManager


class TestSCMFeatures(unittest.TestCase):
    """Validation rigoureuse des fonctionnalités SCM d'architecture logicielle."""

    # =========================================================================
    # 1. TESTS VOLET 1 : JOURNALISATION (LOGGING & AUDIT TRAIL)
    # =========================================================================

    def test_01_logger_structured_json_and_correlation_id(self):
        """Vérifie que le logger émet du JSON valide avec injection du correlation_id."""
        correlation_id_ctx.set("test_trace_uuid_9999")
        current_user_ctx.set("admin_pluvio")

        from cartagen.infrastructure.logging.logger import JsonFormatter
        import logging

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="cartagen.agents.sig",
            level=logging.INFO,
            pathname="sig_generator_agent.py",
            lineno=120,
            msg="Génération cartographique 300 DPI complétée avec succès",
            args=(),
            exc_info=None
        )
        json_output = formatter.format(record)
        parsed = json.loads(json_output)

        self.assertEqual(parsed["correlation_id"], "test_trace_uuid_9999")
        self.assertEqual(parsed["user"], "admin_pluvio")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["logger"], "cartagen.agents.sig")
        self.assertEqual(parsed["message"], "Génération cartographique 300 DPI complétée avec succès")
        self.assertIn("timestamp", parsed)

    def test_02_sensitive_data_masking(self):
        """Vérifie que les clés d'API et tokens privés sont masqués automatiquement."""
        sec_filter = SensitiveDataFilter()
        import logging

        record = logging.LogRecord(
            name="test.sec",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Appel avec GROQ_API_KEY=gsk_SecretToken12345678901234567890 et HF_TOKEN=hf_PrivateSecret12345678901234567890",
            args=(),
            exc_info=None
        )
        sec_filter.filter(record)
        self.assertNotIn("gsk_SecretToken12345678901234567890", record.msg)
        self.assertNotIn("hf_PrivateSecret12345678901234567890", record.msg)
        self.assertIn("***MASKED***", record.msg)

    def test_03_audit_trail_immutable_checksum(self):
        """Vérifie l'enregistrement d'audit et la certification par empreinte SHA-256."""
        audit = AuditLogger()
        entry = audit.log_event(
            action="UPDATE_ENV_PARAM",
            resource="config:.env",
            status="SUCCESS",
            ip_address="192.168.1.100",
            details={"param": "LLM_PROVIDER", "new_val": "groq"}
        )

        self.assertIn("checksum_sha256", entry)
        self.assertEqual(len(entry["checksum_sha256"]), 64)
        self.assertEqual(entry["action"], "UPDATE_ENV_PARAM")
        self.assertEqual(entry["status"], "SUCCESS")

    # =========================================================================
    # 2. TESTS VOLET 2 : GESTION DES VERSIONS (SEMVER & MIGRATIONS)
    # =========================================================================

    def test_04_semver_metadata(self):
        """Vérifie la conformité SemVer 2.0 (MAJOR.MINOR.PATCH)."""
        meta = get_version_metadata()
        self.assertEqual(meta["version"], "1.2.0")
        self.assertEqual(meta["semver"], "1.2.0")
        self.assertEqual(meta["release_stage"], "stable")
        self.assertEqual(meta["codename"], "Hydrologic-SCM")
        self.assertIn("git_commit", meta)
        self.assertIn("spec_standard", meta)

    def test_05_alembic_migrations_discovery(self):
        """Vérifie que les révisions Alembic (001 et 002) sont détectées et valides."""
        mgr = DatabaseMigrationManager()
        revs = mgr.get_available_revisions()
        rev_ids = [r["revision"] for r in revs]

        self.assertIn("001_initial_schema", rev_ids)
        self.assertIn("002_audit_and_locking", rev_ids)

    # =========================================================================
    # 3. TESTS VOLET 3 : GESTION DES CONFLITS (CONCURRENCE RUNTIME)
    # =========================================================================

    def test_06_optimistic_locking_conflict_detection(self):
        """Vérifie la détection du Lost Update et la levée d'OptimisticLockConflictError."""
        lock_mgr = OptimisticLockManager()
        res_id = "config_pluvio_seuil_alerte"

        # 1. Enregistrement initial (Version 1)
        record1 = lock_mgr.register_or_get(res_id, {"seuil_mm": 50.0})
        self.assertEqual(record1["version"], 1)

        # 2. Utilisateur A effectue une mise à jour valide (attend version 1)
        record2 = lock_mgr.update_resource(
            resource_id=res_id,
            new_data={"seuil_mm": 75.0},
            expected_version=1,
            user="expert_hydrologue_A"
        )
        self.assertEqual(record2["version"], 2)
        self.assertEqual(record2["data"]["seuil_mm"], 75.0)

        # 3. Utilisateur B tente une mise à jour concurrente basée sur l'ancienne version 1
        with self.assertRaises(OptimisticLockConflictError) as ctx:
            lock_mgr.update_resource(
                resource_id=res_id,
                new_data={"seuil_mm": 60.0},
                expected_version=1,  # Obsolète !
                user="expert_hydrologue_B"
            )

        err = ctx.exception
        self.assertEqual(err.resource_id, res_id)
        self.assertEqual(err.current_version, 2)
        self.assertEqual(err.expected_version, 1)
        self.assertIn("Conflit de concurrence", str(err))

    def test_07_pessimistic_lock_mutex(self):
        """Vérifie l'exclusion mutuelle stricte sur les traitements par lots lourds."""
        mutex_mgr = TaskMutexManager()
        task_id = "compilation_annuaire_national_2024"

        # 1. Premier travailleur acquiert le verrou exclusif
        acquired = mutex_mgr.acquire_lock(task_id, owner="worker_node_1", timeout_seconds=60)
        self.assertTrue(acquired)
        self.assertTrue(mutex_mgr.is_locked(task_id))

        # 2. Deuxième travailleur tente d'acquérir le même verrou simultanément
        with self.assertRaises(JobAlreadyRunningError) as ctx:
            mutex_mgr.acquire_lock(task_id, owner="worker_node_2", timeout_seconds=60)

        self.assertIn("déjà en cours d'exécution", str(ctx.exception))

        # 3. Libération du verrou par le premier travailleur
        released = mutex_mgr.release_lock(task_id)
        self.assertTrue(released)
        self.assertFalse(mutex_mgr.is_locked(task_id))

        # 4. Nouvelle acquisition autorisée après libération
        acquired_again = mutex_mgr.acquire_lock(task_id, owner="worker_node_2", timeout_seconds=60)
        self.assertTrue(acquired_again)
        mutex_mgr.release_lock(task_id)


if __name__ == "__main__":
    unittest.main()

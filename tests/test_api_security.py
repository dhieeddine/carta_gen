# -*- coding: utf-8 -*-
"""Tests unitaires de sécurité pour les endpoints de l'API FastAPI."""

import unittest
from fastapi.testclient import TestClient
from cartagen.infrastructure.api.app import app

class TestAPISecurity(unittest.TestCase):
    """Vérifie la résistance des routes HTTP aux attaques de type Path Traversal."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_path_traversal_yearbook_download_blocked(self):
        # Tentative d'accès à des fichiers hors du dossier sandbox
        response = self.client.get("/api/v1/yearbook/download/../../.env")
        self.assertIn(response.status_code, [400, 404])

    def test_path_traversal_yearbook_non_pdf_rejected(self):
        # Tentative de téléchargement d'un fichier non-PDF
        response = self.client.get("/api/v1/yearbook/download/sensitive_script.py")
        self.assertEqual(response.status_code, 400)

    def test_path_traversal_map_image_blocked(self):
        # Tentative d'accès au code source ou fichiers système
        response = self.client.get("/api/v1/maps/image/../../run_app.py")
        self.assertEqual(response.status_code, 404)

    def test_invalid_folder_annuaire_image_blocked(self):
        # Dossier ne respectant pas la regex autorisée
        response = self.client.get("/api/v1/annuaire/image/system32/cmd.png")
        self.assertEqual(response.status_code, 400)

    def test_cors_headers_present(self):
        # Requête OPTIONS de pre-flight CORS
        response = self.client.options(
            "/api/v1/maps/generate",
            headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"}
        )
        self.assertEqual(response.status_code, 200)

if __name__ == "__main__":
    unittest.main()

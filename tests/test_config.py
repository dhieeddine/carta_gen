# -*- coding: utf-8 -*-
"""Tests unitaires pour la configuration centralisée."""

import unittest
from cartagen.infrastructure.config import Settings, get_settings

class TestConfig(unittest.TestCase):
    """Vérifie la validation des configurations de l'application."""

    def test_settings_instantiation(self):
        settings = get_settings()
        self.assertIsNotNone(settings.database_url)
        self.assertIn("postgresql://", settings.database_url)

    def test_settings_defaults(self):
        s = Settings()
        self.assertEqual(s.log_level, "INFO")
        self.assertIn("5432", s.database_url)

if __name__ == "__main__":
    unittest.main()

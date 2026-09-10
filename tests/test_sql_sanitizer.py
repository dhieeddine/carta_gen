# -*- coding: utf-8 -*-
"""Tests unitaires pour la sanitisation SQL et la prévention des injections."""

import unittest
from cartagen.infrastructure.agents.sql_generator_agent import _sanitize_sql_string, SQLGeneratorAgent

class TestSQLSanitizer(unittest.TestCase):
    """Vérifie la robustesse de la sanitisation SQL."""

    def test_sanitize_normal_string(self):
        self.assertEqual(_sanitize_sql_string("Tunis"), "Tunis")
        self.assertEqual(_sanitize_sql_string("Ben Arous"), "Ben Arous")
        self.assertEqual(_sanitize_sql_string("Sidi Bouzid"), "Sidi Bouzid")

    def test_sanitize_single_quotes(self):
        # Injection typique ' OR '1'='1 -> guillemets doublés pour l'échappement SQL
        result = _sanitize_sql_string("Tunis' OR '1'='1")
        self.assertEqual(result, "Tunis'' OR ''1''''1")

    def test_sanitize_sql_comments_and_semicolon(self):
        # Injection avec point-virgule et commentaire --
        result = _sanitize_sql_string("Bizerte; DROP TABLE pluies_148; --")
        self.assertNotIn(";", result)
        self.assertNotIn("--", result)
        self.assertEqual(result, "Bizerte DROP TABLE pluies148")

    def test_sanitize_special_chars(self):
        result = _sanitize_sql_string("Station<script>alert(1)</script>!@#$%^&*()")
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        self.assertNotIn("$", result)
        self.assertEqual(result, "Stationscriptalert1script")

    def test_deterministic_parser_valid_query(self):
        agent = SQLGeneratorAgent(gouv_col="lib_fr", reg_col="libelle")
        result = agent._generate_query_deterministic("carte pluviometrique 2021")
        self.assertIsNotNone(result)
        sql, target = result
        self.assertIn("2021", sql)
        self.assertEqual(target, "total")

    def test_deterministic_parser_sql_injection_attempt(self):
        agent = SQLGeneratorAgent(gouv_col="lib_fr", reg_col="libelle")
        result = agent._generate_query_deterministic("carte pluviometrique Tunis' UNION SELECT * FROM users; -- 2021")
        if result is not None:
            sql, _ = result
            # La requête ne doit pas contenir de guillemet simple non échappé ni de point-virgule
            self.assertNotIn(";", sql.rstrip(";"))
            self.assertNotIn("--", sql)

if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Tests unitaires pour le chargeur de squelettes SIG."""

import unittest
from cartagen.infrastructure.agents.skeletons.skeleton_loader import load_skeleton, SKELETONS_DIR

class TestSkeletonLoader(unittest.TestCase):
    """Vérifie le chargement des templates de code SIG."""

    def test_load_existing_skeletons(self):
        templates = [
            "mono", "analysis", "single_gouv", "compare_gouv",
            "region_hydro", "difference", "anomalie",
            "stations_density", "region_naturelle"
        ]
        for name in templates:
            content = load_skeleton(name)
            self.assertIsInstance(content, str)
            self.assertGreater(len(content), 100, f"Template {name} is suspiciously short")

    def test_load_nonexistent_skeleton_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_skeleton("nonexistent_unknown_template")

    def test_coordinates_are_xy(self):
        # Vérifie qu'aucun template n'utilise lon/lat au lieu de x/y
        for name in ["difference", "anomalie", "stations_density"]:
            content = load_skeleton(name)
            self.assertNotIn("['lon', 'lat']", content, f"lon/lat found in {name}")
            self.assertNotIn("['lon']", content, f"['lon'] found in {name}")
            self.assertNotIn("['lat']", content, f"['lat'] found in {name}")

if __name__ == "__main__":
    unittest.main()

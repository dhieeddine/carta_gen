# -*- coding: utf-8 -*-
"""Tests unitaires pour l'analyse statique AST du Sandbox Manager."""

import unittest
from cartagen.infrastructure.sandbox.sandbox_manager import CodeSecurityValidator

class TestCodeSecurityValidator(unittest.TestCase):
    """Vérifie la détection et le blocage de code dangereux par AST."""

    def test_safe_gis_code(self):
        safe_code = """
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np

df = pd.DataFrame({'x': [10.1, 10.2], 'y': [36.8, 36.9], 'val': [50, 100]})
plt.figure()
plt.scatter(df['x'], df['y'])
plt.savefig('output_isohyete.png')
plt.close()
"""
        is_safe, reason = CodeSecurityValidator.validate(safe_code)
        self.assertTrue(is_safe, f"Safe code was incorrectly blocked: {reason}")

    def test_blocked_import_subprocess(self):
        code = "import subprocess\nsubprocess.run(['dir'])"
        is_safe, reason = CodeSecurityValidator.validate(code)
        self.assertFalse(is_safe)
        self.assertIn("subprocess", reason)

    def test_blocked_from_import_socket(self):
        code = "from socket import socket\ns = socket()"
        is_safe, reason = CodeSecurityValidator.validate(code)
        self.assertFalse(is_safe)
        self.assertIn("socket", reason)

    def test_blocked_eval_call(self):
        code = "x = eval('1 + 1')"
        is_safe, reason = CodeSecurityValidator.validate(code)
        self.assertFalse(is_safe)
        self.assertIn("eval", reason)

    def test_blocked_exec_call(self):
        code = "exec('import os')"
        is_safe, reason = CodeSecurityValidator.validate(code)
        self.assertFalse(is_safe)
        self.assertIn("exec", reason)

    def test_blocked_os_system_call(self):
        code = "import os\nos.system('calc.exe')"
        is_safe, reason = CodeSecurityValidator.validate(code)
        self.assertFalse(is_safe)
        self.assertIn("system", reason)

    def test_blocked_shutil_rmtree(self):
        code = "import shutil\nshutil.rmtree('/')"
        is_safe, reason = CodeSecurityValidator.validate(code)
        self.assertFalse(is_safe)
        self.assertIn("shutil", reason)

    def test_syntax_error_rejected(self):
        invalid_code = "def broken_code(: print('oops')"
        is_safe, reason = CodeSecurityValidator.validate(invalid_code)
        self.assertFalse(is_safe)
        self.assertIn("syntaxe", reason.lower())

if __name__ == "__main__":
    unittest.main()

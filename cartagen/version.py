# -*- coding: utf-8 -*-
"""
cartagen/version.py
===================
Gestion du Versioning Sémantique (Semantic Versioning 2.0.0 - SemVer).
Définit la version sous la forme : MAJOR.MINOR.PATCH
- MAJOR : Modifications incompatibles de l'API ou des modèles géospatiaux.
- MINOR : Ajout de fonctionnalités rétrocompatibles (nouvel agent, support nouveau format).
- PATCH : Corrections de bugs rétrocompatibles (sanitizer AST, regex, correctifs).
"""

import os
import subprocess
from typing import Dict, Any

__version__ = "1.2.0"
VERSION_INFO = {
    "major": 1,
    "minor": 2,
    "patch": 0,
    "release_stage": "stable",
    "codename": "Hydrologic-SCM"
}


def get_git_commit_hash() -> str:
    """Tente de récupérer le hash du commit Git courant de manière sécurisée."""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=current_dir,
            stderr=subprocess.DEVNULL
        ).decode("ascii").strip()
        return commit
    except Exception:
        return "git-unavailable"


def get_version_metadata() -> Dict[str, Any]:
    """Retourne la métadonnée complète de version pour l'API et le monitoring."""
    return {
        "version": __version__,
        "semver": f"{VERSION_INFO['major']}.{VERSION_INFO['minor']}.{VERSION_INFO['patch']}",
        "release_stage": VERSION_INFO["release_stage"],
        "codename": VERSION_INFO["codename"],
        "git_commit": get_git_commit_hash(),
        "spec_standard": "Semantic Versioning 2.0.0 (https://semver.org/)"
    }


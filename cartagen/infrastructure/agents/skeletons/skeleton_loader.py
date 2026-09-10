# -*- coding: utf-8 -*-
"""Chargeur centralisé des squelettes de code SIG.

Charge les fichiers .py.template depuis le dossier skeletons/ et les met en cache
pour éviter les lectures disque répétées.
"""

import os
from functools import lru_cache

SKELETONS_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=20)
def load_skeleton(skeleton_name: str) -> str:
    """Charge un squelette de code depuis le fichier .py.template correspondant.

    Args:
        skeleton_name: Nom du squelette (ex: 'mono', 'single_gouv', 'analysis').
                       Correspond au nom du fichier sans l'extension .py.template.

    Returns:
        str: Contenu du template Python.
        
    Raises:
        FileNotFoundError: Si le fichier template n'existe pas.
    """
    template_path = os.path.join(SKELETONS_DIR, f"{skeleton_name}.py.template")
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Squelette introuvable : {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

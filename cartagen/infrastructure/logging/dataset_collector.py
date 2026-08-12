# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/logging/dataset_collector.py
======================================================
Collecteur automatique des paires (Prompt ➔ Code Corrige / Requête SQL Valide)
pour enrichir en continu le jeu de données de Fine-Tuning LoRA.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

class DatasetCollector:
    """Agent d'enregistrement des paires corrigées pour le ré-entraînement LoRA."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.dataset_dir = os.path.join(workspace_root, "lora_dataset_collector")
        os.makedirs(self.dataset_dir, exist_ok=True)
        self.jsonl_file = os.path.join(self.dataset_dir, "lora_reinforced_dataset.jsonl")

    def record_successful_pair(self, prompt: str, sql_query: str, python_code: str, provider: str, was_corrected: bool = False, original_error: str = ""):
        """Enregistre un exemple d'entraînement valide au format JSONL ChatML pour vLLM / Unsloth / HuggingFace."""
        try:
            record = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "provider": provider,
                "was_corrected": was_corrected,
                "original_error": original_error[:300] if original_error else "",
                "messages": [
                    {
                        "role": "system",
                        "content": "Tu es un expert SIG Python, PostGIS et SQL pour la DGRE Tunisie (CartaGen). Génère du code Python et SQL 100% autonome, fonctionnel et sans erreurs."
                    },
                    {
                        "role": "user",
                        "content": f"Instruction : {prompt}\nRequête SQL : {sql_query}"
                    },
                    {
                        "role": "assistant",
                        "content": python_code
                    }
                ]
            }

            with open(self.jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            print(f"[DatasetCollector] 💾 Paire validée enregistrée dans '{self.jsonl_file}' (Corrigée: {was_corrected})")
        except Exception as e:
            print(f"[DatasetCollector] ⚠️ Erreur lors de l'enregistrement de la paire d'entraînement : {e}")

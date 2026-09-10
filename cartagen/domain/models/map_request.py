# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class MapRequest:
    """Représente une demande de carte soumise par l'utilisateur."""
    prompt: str
    request_id: str
    created_at: datetime
    user_id: Optional[str] = None
    custom_specifications: Optional[Dict[str, Any]] = None
    use_rag: bool = True

@dataclass
class ExecutionResult:
    """Représente le résultat de l'exécution du code dans la Sandbox."""
    success: bool
    stdout: str
    stderr: str
    output_image_path: Optional[str]
    error_message: Optional[str] = None
    execution_time: float = 0.0
    output_table_html: Optional[str] = None

@dataclass
class GeneratedMap:
    """Représente la carte générée avec son code et ses métadonnées."""
    request_id: str
    prompt: str
    prompt_type: str  # mono, compare, difference, etc.
    python_code: str
    sql_query: Optional[str]
    image_url: Optional[str]
    created_at: datetime
    execution_details: ExecutionResult
    table_html: Optional[str] = None
    agent_traces: Optional[Dict[str, Any]] = None

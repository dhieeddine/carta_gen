# -*- coding: utf-8 -*-
"""
cartagen/domain/models/agent_message_bus.py
============================================
Bus de communication et traçabilité inter-agents pour CartaGen.
Permet d'échanger des messages, des requêtes de validation et des alertes d'auto-correction.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional

class AgentMessage:
    """Représente un message individuel échangé entre deux agents."""

    def __init__(
        self,
        sender: str,
        receiver: str,
        action: str,
        payload: Dict[str, Any],
        status: str = "INFO",
        description: str = ""
    ):
        self.sender = sender
        self.receiver = receiver
        self.action = action
        self.payload = payload
        self.status = status  # INFO, SUCCESS, WARNING, ERROR
        self.description = description
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "action": self.action,
            "payload": self.payload,
            "status": self.status,
            "description": self.description,
            "timestamp": self.timestamp
        }


class AgentMessageBus:
    """Bus central gérant l'historique et la transmission des messages inter-agents."""

    def __init__(self):
        self.messages: List[AgentMessage] = []

    def publish(self, message: AgentMessage):
        """Publie un nouveau message sur le bus."""
        self.messages.append(message)
        print(f"[{message.sender} ➔ {message.receiver}] [{message.status}] {message.action}: {message.description}")

    def get_traces(self) -> List[Dict[str, Any]]:
        """Retourne la liste complète des traces pour l'interface utilisateur."""
        return [m.to_dict() for m in self.messages]

    def clear(self):
        """Réinitialise les traces du bus."""
        self.messages.clear()

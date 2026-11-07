# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/logging/middleware.py
=============================================
Middleware de Corrélation et Observabilité ASGI pour FastAPI.
Implémentation ASGI pure (haute performance, non-bloquante, sans deadlock TestClient) :
- Extrait ou génère l'identifiant unique `X-Request-ID`
- Lie le correlation_id au contexte asynchrone (ContextVars)
- Mesure la latence avec haute précision
- Injecte `X-Request-ID` et `X-Response-Time-Ms` dans les en-têtes HTTP de réponse
- Émet un log d'accès structuré JSON
"""

import time
import uuid
from cartagen.infrastructure.logging.logger import (
    correlation_id_ctx,
    current_user_ctx,
    setup_logger
)

access_logger = setup_logger("cartagen.http_access")


class CorrelationIdMiddleware:
    """Middleware ASGI d'injection et de traçabilité des Correlation IDs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # Extraction des en-têtes de la requête ASGI
        raw_headers = dict(scope.get("headers", []))
        req_id = None
        user = "anonymous_user"

        for k, v in raw_headers.items():
            k_lower = k.lower()
            if k_lower in (b"x-request-id", b"x-correlation-id"):
                req_id = v.decode("latin1", errors="replace")
            elif k_lower == b"x-user-id":
                user = v.decode("latin1", errors="replace")

        if not req_id:
            req_id = f"req_{uuid.uuid4().hex[:12]}"

        # Liaison au contexte d'exécution
        corr_token = correlation_id_ctx.set(req_id)
        user_token = current_user_ctx.set(user)
        start_time = time.perf_counter()

        status_code_holder = [200]

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                status_code_holder[0] = message.get("status", 200)
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-request-id", req_id.encode("latin1")))
                headers_list.append((b"x-response-time-ms", str(duration_ms).encode("latin1")))
                message["headers"] = headers_list
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            method = scope.get("method", "GET")
            path = scope.get("path", "/")
            access_logger.info(
                f"{method} {path} -> {status_code_holder[0]} ({duration_ms}ms)",
                extra={"extra_data": {
                    "method": method,
                    "path": path,
                    "status_code": status_code_holder[0],
                    "duration_ms": duration_ms
                }}
            )
        finally:
            correlation_id_ctx.reset(corr_token)
            current_user_ctx.reset(user_token)

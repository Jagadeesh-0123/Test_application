import secrets
from collections.abc import Callable
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    public_paths = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        if request.url.path not in self.public_paths:
            expected_key = settings.API_KEY_SECRET
            supplied_key = request.headers.get("X-Api-Key", "")
            if not expected_key or not secrets.compare_digest(
                supplied_key.encode("utf-8"), expected_key.encode("utf-8")
            ):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )

        return await call_next(request)
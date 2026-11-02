import logging
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request

from app.config import settings
from app.database import Base, engine
from app.middleware import ApiKeyMiddleware
from app.routers import inventory


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


handler = logging.StreamHandler()
handler.setFormatter(JsonLogFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Application started and database initialized.")
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(ApiKeyMiddleware)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        process_time_ms = int((time.perf_counter() - start_time) * 1000)
    response.headers["X-Response-Time-Ms"] = str(process_time_ms)
    return response

app.include_router(inventory.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

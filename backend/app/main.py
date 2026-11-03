import json
import logging
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from app.api import outbox, planning, requests, respond
from app.api.routes import router
from app.config import get_settings


class JsonFormatter(logging.Formatter):
    """Journalisation structurée (NF-14)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Planning ATS", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )

    @app.exception_handler(StaleDataError)
    async def _stale(_request: Request, _exc: StaleDataError) -> JSONResponse:
        # R-12 : écriture concurrente, le front doit recharger
        return JSONResponse(
            status_code=409,
            content={"detail": "Donnée modifiée par un autre utilisateur, rechargez la page."},
        )

    app.include_router(router)
    app.include_router(planning.router)
    app.include_router(requests.router)
    app.include_router(outbox.router)
    app.include_router(respond.router)
    return app


app = create_app()

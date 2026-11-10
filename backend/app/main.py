"""KAAMSETU FastAPI application."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import health
from app.api.v1.router import api_router
from app.config import get_settings
from app.core.errors import error_body, register_exception_handlers
from app.core.logging import configure_logging

logger = logging.getLogger("kaamsetu.http")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        secrets=(settings.gnani_api_key.get_secret_value(), settings.jwt_secret_key.get_secret_value()),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logging.getLogger("kaamsetu").info(
            "Starting KAAMSETU backend",
            extra={"ctx": {"env": settings.app_env, "gnani_configured": settings.gnani_configured}},
        )
        yield

    app = FastAPI(
        title="KAAMSETU API",
        version=settings.app_version,
        description="Voice-first field workforce platform. Speech by Gnani Prisma and Timbre.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # bearer tokens in headers; no cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id[:64]

        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content=error_body(
                    "payload_too_large",
                    f"Request body exceeds {settings.max_audio_upload_mb} MB",
                ),
                headers={"X-Request-ID": request.state.request_id},
            )

        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "request",
            extra={
                "ctx": {
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                }
            },
        )
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    # Unversioned liveness probe for Docker / load balancers.
    app.add_api_route("/health", health.health, methods=["GET"], include_in_schema=False)
    return app


app = create_app()

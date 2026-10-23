"""Main FastAPI Application Entrypoint.

Conforms to Phase 0 requirements:
- Request ID generation and propagation
- Structured logging middleware
- Global structured exception handling
- Health endpoints at /health, /health/live, /health/ready
- API versioning mounted at /api/v1
- CORS support for frontend clients
"""

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.v1.endpoints.health import router as root_health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import logger, request_id_ctx, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()
    setup_logging(level="DEBUG" if settings.debug else "INFO")
    logger.info(
        f"Starting {settings.app_name} v{settings.app_version} [env={settings.app_env}]"
    )
    yield
    from app.core.redis import close_redis
    from app.db.session import dispose_engine

    await close_redis()
    await dispose_engine()
    logger.info(f"Shutting down {settings.app_name}")


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates X-Request-ID and logs request lifecycle."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        logger.info(
            f"Incoming request {request.method} {request.url.path}",
            extra={"request_id": req_id},
        )

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = req_id

            logger.info(
                f"Request completed {request.method} {request.url.path} "
                f"status={response.status_code} duration={duration_ms}ms",
                extra={"request_id": req_id},
            )
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                f"Request failed {request.method} {request.url.path} "
                f"duration={duration_ms}ms",
                extra={"request_id": req_id},
            )
            raise
        finally:
            request_id_ctx.reset(token)


def create_application() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestTracingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handlers
    register_error_handlers(app)

    # Direct Health Probes (conforms to root /health, /health/live, /health/ready)
    app.include_router(root_health_router)

    # Versioned API routes (/api/v1/...)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_application()

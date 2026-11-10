import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.core.deps import DbSession
from app.core.errors import error_body

router = APIRouter(tags=["health"])
logger = logging.getLogger("kaamsetu.health")


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        # Whether a key is present - never the key itself.
        "gnani_configured": settings.gnani_configured,
    }


@router.get("/health/db")
def health_db(db: DbSession):
    try:
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        return JSONResponse(status_code=503, content=error_body("database_unavailable", "Database is not reachable"))
    return {"status": "ok", "database": "ok", "migration_revision": revision}

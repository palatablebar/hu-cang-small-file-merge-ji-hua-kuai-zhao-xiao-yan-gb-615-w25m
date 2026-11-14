from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import SNAPSHOT_VERIFY_ROLES
from src.controllers import snapshot_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.snapshot import VerifyIn
from src.services import snapshot_service
from src.utils.pagination import page_params

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("")
def list_pairs(
    table_id: int | None = None,
    verdict: str | None = None,
    limit: int = Query(30),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return snapshot_controller.list_pairs(db, table_id=table_id, verdict=verdict, limit=page.limit, offset=page.offset)


@router.get("/stats")
def snapshot_stats(
    db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return snapshot_service.snapshot_stats(db)


@router.get("/{snapshot_id}")
def get_snapshot(
    snapshot_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return snapshot_controller.get_snapshot(db, snapshot_id)


@router.post("/verify")
def verify(
    payload: VerifyIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*SNAPSHOT_VERIFY_ROLES)),
) -> dict:
    return snapshot_controller.verify(db, payload.model_dump(), principal, request)

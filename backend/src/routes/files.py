from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import SCAN_ROLES
from src.controllers import file_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.services import data_file_service
from src.utils.pagination import page_params

router = APIRouter(prefix="/files", tags=["files"])


class ScanIn(BaseModel):
    table_id: int | None = Field(default=None, ge=1)


@router.get("")
def list_files(
    table_id: int | None = None,
    partition_id: int | None = None,
    kind: str | None = None,
    q: str | None = None,
    small_only: bool = False,
    limit: int = Query(30),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return file_controller.list_files(
        db,
        table_id=table_id,
        partition_id=partition_id,
        kind=kind,
        q=q,
        small_only=small_only,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/stats")
def file_stats(
    table_id: int | None = None,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return data_file_service.file_stats(db, table_id)


@router.post("/scan")
def scan(
    payload: ScanIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*SCAN_ROLES)),
) -> dict:
    return file_controller.scan(db, payload.model_dump(), principal, request)

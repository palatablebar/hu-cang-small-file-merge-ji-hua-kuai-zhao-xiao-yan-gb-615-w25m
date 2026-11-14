from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import TABLE_WRITE_ROLES
from src.controllers import table_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.table import TableIn, TablePatch
from src.utils.pagination import page_params

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("")
def list_tables(
    q: str | None = None,
    layer: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return table_controller.list_tables(db, q=q, layer=layer, enabled=enabled, limit=page.limit, offset=page.offset)


@router.get("/{table_id}")
def get_table(
    table_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return table_controller.get_table(db, table_id)


@router.post("", status_code=201)
def create_table(
    payload: TableIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*TABLE_WRITE_ROLES)),
) -> dict:
    return table_controller.create_table(db, payload.model_dump(), principal, request)


@router.patch("/{table_id}")
def update_table(
    table_id: int,
    payload: TablePatch,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*TABLE_WRITE_ROLES)),
) -> dict:
    return table_controller.update_table(db, table_id, payload.model_dump(exclude_unset=True), principal, request)

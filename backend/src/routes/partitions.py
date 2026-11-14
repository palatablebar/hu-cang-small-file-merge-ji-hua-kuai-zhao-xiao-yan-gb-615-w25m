from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.middlewares.rbac import READ_ROLES, require_roles
from src.services import partition_service
from src.utils.pagination import page_params

router = APIRouter(prefix="/partitions", tags=["partitions"])


@router.get("")
def list_partitions(
    table_id: int | None = None,
    layer: str | None = None,
    needs_rewrite: bool | None = None,
    q: str | None = None,
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return partition_service.list_partitions(
        db,
        table_id=table_id,
        layer=layer,
        needs_rewrite=needs_rewrite,
        q=q,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/stats")
def partition_stats(
    table_id: int | None = None,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return partition_service.partition_stats(db, table_id)

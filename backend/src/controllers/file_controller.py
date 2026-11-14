"""文件清单控制器：manifest 明细分页 + 扫描重算。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, data_file_service


def list_files(db: Session, **filters) -> dict:
    return data_file_service.list_files(db, **filters)


def scan(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    result = data_file_service.scan(db, payload.get("table_id"))
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="file.scan",
        entity="lake_table",
        entity_id=payload.get("table_id"),
        detail=result,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result

"""导出控制器：CSV 响应 + 审计。"""
from __future__ import annotations

from fastapi import Request, Response
from sqlalchemy.orm import Session

from src.services import audit_service, export_service
from src.utils.csv_export import csv_response_headers


def plans_csv(db: Session, table_id: int | None, principal: dict, request: Request) -> Response:
    content = export_service.plans_csv(db, table_id=table_id)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.plans",
        entity="compaction_job",
        entity_id=table_id,
        detail={"bytes": len(content)},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=csv_response_headers("compaction-plans.csv"))


def snapshots_csv(db: Session, table_id: int | None, principal: dict, request: Request) -> Response:
    content = export_service.snapshots_csv(db, table_id=table_id)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.snapshots",
        entity="snapshot",
        entity_id=table_id,
        detail={"bytes": len(content)},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=csv_response_headers("snapshot-verify.csv"))

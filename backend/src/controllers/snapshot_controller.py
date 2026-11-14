"""快照控制器：成对列表、明细、守恒校验。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, snapshot_service


def list_pairs(db: Session, **filters) -> dict:
    return snapshot_service.list_pairs(db, **filters)


def get_snapshot(db: Session, snapshot_id: int) -> dict:
    return snapshot_service.get_detail(db, snapshot_id)


def verify(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    result = snapshot_service.verify_pair(db, payload["before_id"], payload["after_id"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="snapshot.verify",
        entity="snapshot",
        entity_id=payload["after_id"],
        detail={
            "verdict": result.get("verdict"),
            "rows_delta": result.get("rows_delta"),
            "added": (result.get("counts") or {}).get("added"),
            "removed": (result.get("counts") or {}).get("removed"),
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result

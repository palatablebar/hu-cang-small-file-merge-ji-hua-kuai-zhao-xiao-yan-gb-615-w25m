"""合并计划控制器：立项、执行、窗口重排、复核。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, job_service
from src.utils.errors import AppError


def list_jobs(db: Session, *, role: str, **filters) -> dict:
    return job_service.list_jobs(db, role=role, **filters)


def get_job(db: Session, job_id: int, role: str) -> dict:
    return job_service.get_job_detail(db, job_id, role)


def create_job(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    job = job_service.create_plan(db, payload, operator_email=principal["email"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="plan.create",
        entity="compaction_job",
        entity_id=job.id,
        detail={
            "plan_no": job.plan_no,
            "groups": len(job.merge_groups or []),
            "conflict": (job.conflict or {}).get("conflict"),
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return job_service.get_job_detail(db, job.id, principal["role"])


def execute_job(db: Session, job_id: int, principal: dict, request: Request) -> dict:
    job = job_service.get_job(db, job_id)
    result = job_service.execute_job(db, job, actor_email=principal["email"])
    if result["blocked"]:
        audit_service.record(
            db,
            actor_email=principal["email"],
            actor_role=principal["role"],
            action="plan.block",
            entity="compaction_job",
            entity_id=job.id,
            detail={"plan_no": job.plan_no, "reason": result["reason"]},
            ip=request.client.host if request.client else None,
        )
        db.commit()
        raise AppError(
            "CONFLICT",
            409,
            {
                "reason": result["reason"],
                "plan_no": job.plan_no,
                "status": job.status,
                "verify": job.verify,
            },
            message="快照守恒校验或流读窗口门禁未通过，已阻止执行",
        )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="plan.execute",
        entity="compaction_job",
        entity_id=job.id,
        detail={
            "plan_no": job.plan_no,
            "verdict": (job.verify or {}).get("verdict"),
            "after_snapshot": job.after_snapshot_id,
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return job_service.get_job_detail(db, job.id, principal["role"])


def reschedule(db: Session, job_id: int, payload: dict, principal: dict, request: Request) -> dict:
    job = job_service.get_job(db, job_id)
    job_service.update_window(db, job, window_start=payload["window_start"], window_end=payload["window_end"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="plan.create",
        entity="compaction_job",
        entity_id=job.id,
        detail={"plan_no": job.plan_no, "action": "reschedule", "conflict": (job.conflict or {}).get("conflict")},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return job_service.get_job_detail(db, job.id, principal["role"])


def review(db: Session, job_id: int, payload: dict, principal: dict, request: Request) -> dict:
    job = job_service.get_job(db, job_id)
    job_service.review(db, job, status=payload["status"], note=payload.get("note"), reviewer=principal["email"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="plan.review",
        entity="compaction_job",
        entity_id=job.id,
        detail={"plan_no": job.plan_no, "status": job.review_status},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return job_service.get_job_detail(db, job.id, principal["role"])


def window_check(db: Session, job_id: int) -> dict:
    job = job_service.get_job(db, job_id)
    return job_service.window_check(db, job)

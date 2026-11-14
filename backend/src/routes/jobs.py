from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import PLAN_CREATE_ROLES, PLAN_EXECUTE_ROLES, PLAN_REVIEW_ROLES
from src.controllers import job_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.compaction import PlanIn, PlanWindowIn, ReviewIn
from src.utils.pagination import page_params

router = APIRouter(prefix="/compaction-jobs", tags=["compaction"])


@router.get("")
def list_jobs(
    table_id: int | None = None,
    status: str | None = None,
    review_status: str | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return job_controller.list_jobs(
        db,
        role=principal["role"],
        table_id=table_id,
        status=status,
        review_status=review_status,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{job_id}")
def get_job(
    job_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return job_controller.get_job(db, job_id, principal["role"])


@router.get("/{job_id}/window")
def window_check(
    job_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return job_controller.window_check(db, job_id)


@router.post("", status_code=201)
def create_job(
    payload: PlanIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*PLAN_CREATE_ROLES)),
) -> dict:
    return job_controller.create_job(db, payload.model_dump(), principal, request)


@router.post("/{job_id}/execute")
def execute_job(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*PLAN_EXECUTE_ROLES)),
) -> dict:
    return job_controller.execute_job(db, job_id, principal, request)


@router.patch("/{job_id}/window")
def reschedule(
    job_id: int,
    payload: PlanWindowIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*PLAN_CREATE_ROLES)),
) -> dict:
    return job_controller.reschedule(db, job_id, payload.model_dump(), principal, request)


@router.patch("/{job_id}/review")
def review(
    job_id: int,
    payload: ReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*PLAN_REVIEW_ROLES)),
) -> dict:
    return job_controller.review(db, job_id, payload.model_dump(), principal, request)

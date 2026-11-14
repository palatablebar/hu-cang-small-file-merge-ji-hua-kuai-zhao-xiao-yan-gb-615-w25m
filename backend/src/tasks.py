"""Celery 任务：心跳、每日 manifest 重扫（刷新分区聚合，供合并计划刷新候选）。"""
from __future__ import annotations

import time

from sqlalchemy import select

from src.config.celery_app import TASK_DAILY, TASK_HEARTBEAT, celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name=TASK_HEARTBEAT)
def heartbeat() -> str:
    try:
        _redis().set(f"{settings.app_name}:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name=TASK_DAILY)
def daily_rescan() -> dict:
    from src.config.database import session_scope
    from src.models.lake_table import LakeTable
    from src.services import audit_service, data_file_service

    with session_scope() as db:
        tables = db.scalars(select(LakeTable).where(LakeTable.enabled.is_(True))).all()
        result = data_file_service.scan(db)
        audit_service.record(
            db,
            actor_email="scheduler@" + settings.app_name + ".io",
            actor_role="admin",
            action="file.scan",
            entity="lake_table",
            entity_id=None,
            detail={"trigger": "schedule", "tables": len(tables), **result},
            layer="worker",
        )
    logger.info("daily rescan finished: %s tables / %s partitions", result["tables"], result["partitions"])
    return {"tables": result["tables"], "partitions": result["partitions"], "files": result["files"]}

"""总览：小文件规模、待合并、最近收益、快照守恒分布。"""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.constants.enums import (
    JOB_STATUS_LABELS,
    LAYER_LABELS,
    LAYER_ORDER,
    SMALL_FILE_BYTES,
    VERDICT_LABELS,
    VERDICT_ORDER,
)
from src.models.compaction_job import CompactionJob
from src.models.data_file import DataFile
from src.models.lake_table import LakeTable
from src.models.partition import Partition
from src.models.snapshot import Snapshot
from src.services import job_service


def worker_alive() -> bool:
    try:
        import time

        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        value = client.get(f"{settings.app_name}:worker:heartbeat")
        return bool(value) and (time.time() - float(value)) < 120
    except Exception:
        return False


def overview(db: Session, role: str = "viewer") -> dict:
    tables_total = db.scalar(select(func.count()).select_from(LakeTable)) or 0
    partitions_total = db.scalar(select(func.count()).select_from(Partition)) or 0
    files_total = db.scalar(select(func.count()).select_from(DataFile)) or 0
    small_files = db.scalar(select(func.count()).select_from(DataFile).where(DataFile.bytes < SMALL_FILE_BYTES)) or 0
    delete_files = db.scalar(select(func.count()).select_from(DataFile).where(DataFile.kind == "delete")) or 0
    bytes_total = db.scalar(select(func.coalesce(func.sum(DataFile.bytes), 0))) or 0
    rows_total = db.scalar(select(func.coalesce(func.sum(DataFile.rows), 0))) or 0
    rewrite_partitions = db.scalar(select(func.count()).select_from(Partition).where(Partition.needs_rewrite.is_(True))) or 0

    status_rows = db.execute(select(CompactionJob.status, func.count()).group_by(CompactionJob.status)).all()
    status_counts = {key: int(count or 0) for key, count in status_rows}
    pending_review = db.scalar(
        select(func.count()).select_from(CompactionJob).where(CompactionJob.review_status == "pending")
    ) or 0
    planned = status_counts.get("planned", 0)
    executed = status_counts.get("executed", 0)
    blocked = status_counts.get("blocked", 0)

    latest_executed = db.scalar(
        select(CompactionJob).where(CompactionJob.status == "executed").order_by(CompactionJob.executed_at.desc()).limit(1)
    )
    gain = None
    if latest_executed is not None:
        metrics = latest_executed.metrics or {}
        gain = {
            "plan_no": latest_executed.plan_no,
            "io_saved_ratio": metrics.get("io_saved_ratio") or 0.0,
            "files_before": metrics.get("files_before") or 0,
            "expected_files_after": metrics.get("expected_files_after") or 0,
            "files_reduced": metrics.get("files_reduced") or 0,
            "bytes_before": None if role == "viewer" else metrics.get("bytes_before"),
            "rewrite_reclaim_bytes": None if role == "viewer" else metrics.get("rewrite_reclaim_bytes"),
            "avg_fill_ratio": metrics.get("avg_fill_ratio") or 0.0,
            "executed_at": latest_executed.executed_at.isoformat(timespec="seconds") + "Z" if latest_executed.executed_at else None,
        }

    layer_rows = db.execute(
        select(LakeTable.layer, func.count(func.distinct(LakeTable.id)), func.count(DataFile.id))
        .select_from(LakeTable)
        .outerjoin(DataFile, DataFile.table_id == LakeTable.id)
        .group_by(LakeTable.layer)
    ).all()
    layer_map = {layer: (int(tables or 0), int(files or 0)) for layer, tables, files in layer_rows}
    layer_distribution = [
        {
            "key": layer,
            "label": LAYER_LABELS.get(layer, layer),
            "tables": layer_map.get(layer, (0, 0))[0],
            "files": layer_map.get(layer, (0, 0))[1],
        }
        for layer in LAYER_ORDER
    ]

    top_rows = db.execute(
        select(
            LakeTable.code,
            LakeTable.name,
            LakeTable.layer,
            func.count(DataFile.id),
            func.coalesce(func.sum(case((DataFile.bytes < SMALL_FILE_BYTES, 1), else_=0)), 0),
            func.coalesce(func.sum(DataFile.bytes), 0),
        )
        .select_from(DataFile)
        .join(LakeTable, LakeTable.id == DataFile.table_id)
        .group_by(LakeTable.code, LakeTable.name, LakeTable.layer)
        .order_by(func.coalesce(func.sum(case((DataFile.bytes < SMALL_FILE_BYTES, 1), else_=0)), 0).desc())
        .limit(6)
    ).all()
    top_tables = [
        {
            "table_code": code,
            "table_name": name,
            "layer": layer,
            "files": int(files or 0),
            "small_files": int(small or 0),
            "small_ratio": round(int(small or 0) / int(files), 4) if files else 0.0,
            "bytes": None if role == "viewer" else int(total or 0),
        }
        for code, name, layer, files, small, total in top_rows
    ]

    verdict_rows = db.execute(
        select(Snapshot.verdict, func.count()).where(Snapshot.label == "after").group_by(Snapshot.verdict)
    ).all()
    verdict_map = {key or "unverifiable": int(count or 0) for key, count in verdict_rows}
    verdicts = [
        {"key": key, "label": VERDICT_LABELS.get(key, key), "count": verdict_map.get(key, 0)}
        for key in VERDICT_ORDER
    ]

    recent = db.scalars(select(CompactionJob).order_by(CompactionJob.id.desc()).limit(5)).all()
    tables = {table.id: table for table in db.scalars(select(LakeTable)).all()}
    recent_jobs = [job_service.serialize(job, tables.get(job.table_id), role) for job in recent]

    return {
        "tables_total": tables_total,
        "partitions_total": partitions_total,
        "files_total": files_total,
        "small_files": small_files,
        "small_file_ratio": round(small_files / files_total, 4) if files_total else 0.0,
        "small_file_threshold": SMALL_FILE_BYTES,
        "delete_files": delete_files,
        "rewrite_partitions": rewrite_partitions,
        "bytes_total": None if role == "viewer" else int(bytes_total),
        "rows_total": int(rows_total),
        "plans": {
            "total": sum(status_counts.values()),
            "planned": planned,
            "executed": executed,
            "blocked": blocked,
            "pending_review": int(pending_review),
            "status_labels": JOB_STATUS_LABELS,
        },
        "latest_gain": gain,
        "layer_distribution": layer_distribution,
        "top_tables": top_tables,
        "verdicts": verdicts,
        "recent_jobs": recent_jobs,
        "worker_alive": worker_alive(),
    }

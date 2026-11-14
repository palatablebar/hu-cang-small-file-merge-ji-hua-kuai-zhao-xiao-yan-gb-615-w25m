"""合并计划服务：算法 A 立项 → 冲突窗口校验 → 执行模拟 → 算法 B 快照守恒。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    JOB_STATUS_LABELS,
    REVIEW_STATUS_LABELS,
    TRIGGER_LABELS,
    VERDICT_LABELS,
)
from src.constants.limits import MAX_TARGET_BYTES, MIN_TARGET_BYTES
from src.models.compaction_job import CompactionJob
from src.models.data_file import DataFile
from src.models.lake_table import LakeTable
from src.models.partition import Partition
from src.services import compaction_planner, snapshot_service, snapshot_verifier
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc, local_now, utcnow


# ---------------------------------------------------------------- 序列化


def _redact_metrics(metrics: dict) -> dict:
    """viewer 只允许看比例，不允许看绝对收益字节数。"""
    clone = dict(metrics)
    for field in ("bytes_before", "bytes_after", "rewrite_reclaim_bytes"):
        if field in clone:
            clone[field] = None
    clone["numbers_redacted"] = True
    return clone


def serialize(job: CompactionJob, table: LakeTable | None = None, role: str = "admin") -> dict:
    metrics = dict(job.metrics or {})
    groups = list(job.merge_groups or [])
    redacted = role == "viewer"
    if redacted:
        metrics = _redact_metrics(metrics)
        groups = [{**group, "bytes": None} for group in groups]
    return {
        "id": job.id,
        "plan_no": job.plan_no,
        "table_id": job.table_id,
        "table_code": table.code if table else None,
        "table_name": table.name if table else None,
        "layer": table.layer if table else None,
        "trigger": job.trigger,
        "trigger_label": TRIGGER_LABELS.get(job.trigger, job.trigger),
        "status": job.status,
        "status_label": JOB_STATUS_LABELS.get(job.status, job.status),
        "target_bytes": job.target_bytes,
        "target_mb": round(job.target_bytes / 1048576, 1),
        "min_files": job.min_files,
        "flow_lag_seconds": job.flow_lag_seconds,
        "window_start": iso_utc(job.window_start),
        "window_end": iso_utc(job.window_end),
        "operator_email": job.operator_email,
        "metrics": metrics,
        "merge_groups": groups,
        "merge_group_count": len(groups),
        "rewrite_partitions": job.rewrite_partitions or [],
        "skipped_partitions": job.skipped_partitions or [],
        "conflict": job.conflict or {},
        "before_snapshot_id": job.before_snapshot_id,
        "after_snapshot_id": job.after_snapshot_id,
        "verify": job.verify or {},
        "verdict": (job.verify or {}).get("verdict"),
        "verdict_label": VERDICT_LABELS.get((job.verify or {}).get("verdict") or "", "未校验"),
        "review_status": job.review_status,
        "review_status_label": REVIEW_STATUS_LABELS.get(job.review_status, job.review_status),
        "reviewer": job.reviewer,
        "review_note": job.review_note,
        "numbers_redacted": redacted,
        "created_at": iso_utc(job.created_at),
        "executed_at": iso_utc(job.executed_at),
    }


def _table_map(db: Session) -> dict[int, LakeTable]:
    return {table.id: table for table in db.scalars(select(LakeTable)).all()}


# ---------------------------------------------------------------- 查询


def list_jobs(
    db: Session,
    *,
    table_id: int | None = None,
    status: str | None = None,
    review_status: str | None = None,
    role: str = "admin",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stmt = select(CompactionJob)
    count_stmt = select(func.count()).select_from(CompactionJob)
    if table_id:
        stmt = stmt.where(CompactionJob.table_id == table_id)
        count_stmt = count_stmt.where(CompactionJob.table_id == table_id)
    if status:
        stmt = stmt.where(CompactionJob.status == status)
        count_stmt = count_stmt.where(CompactionJob.status == status)
    if review_status:
        stmt = stmt.where(CompactionJob.review_status == review_status)
        count_stmt = count_stmt.where(CompactionJob.review_status == review_status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(CompactionJob.id.desc()).limit(limit).offset(offset)).all()
    tables = _table_map(db)
    return {
        "items": [serialize(row, tables.get(row.table_id), role) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_job(db: Session, job_id: int) -> CompactionJob:
    job = db.get(CompactionJob, job_id)
    if job is None:
        raise not_found("compaction_job", job_id)
    return job


def get_job_detail(db: Session, job_id: int, role: str = "admin") -> dict:
    job = get_job(db, job_id)
    table = db.get(LakeTable, job.table_id)
    payload = serialize(job, table, role)
    if job.before_snapshot_id and job.after_snapshot_id:
        payload["snapshot_pair"] = snapshot_service.verify_pair(db, job.before_snapshot_id, job.after_snapshot_id)
    return payload


def next_plan_no(db: Session) -> str:
    prefix = f"CP{local_now():%Y%m%d}"
    count = db.scalar(select(func.count()).select_from(CompactionJob).where(CompactionJob.plan_no.like(f"{prefix}%"))) or 0
    return f"{prefix}-{count + 1:04d}"


# ---------------------------------------------------------------- 立项（算法 A）


def _partition_payload(db: Session, table_id: int) -> list[dict]:
    partitions = db.scalars(select(Partition).where(Partition.table_id == table_id).order_by(Partition.partition_key)).all()
    files = db.scalars(select(DataFile).where(DataFile.table_id == table_id)).all()
    grouped: dict[int, list[dict]] = {}
    for item in files:
        grouped.setdefault(item.partition_id, []).append(
            {
                "path": item.path,
                "kind": item.kind,
                "bytes": item.bytes,
                "rows": item.rows,
                "checksum": item.checksum,
            }
        )
    return [
        {
            "partition_key": partition.partition_key,
            "layer": "",
            "files": grouped.get(partition.id, []),
        }
        for partition in partitions
    ]


def build_plan_for_table(db: Session, table: LakeTable, *, target_bytes: int | None, min_files: int | None) -> dict:
    partitions = _partition_payload(db, table.id)
    for partition in partitions:
        partition["layer"] = table.layer
    target = int(target_bytes or table.target_bytes)
    minimum = int(min_files or table.min_files)
    if target < MIN_TARGET_BYTES or target > MAX_TARGET_BYTES:
        raise AppError("VALIDATION", 422, {"field": "target_bytes", "min": MIN_TARGET_BYTES, "max": MAX_TARGET_BYTES})
    return compaction_planner.build_plan(partitions, target_bytes=target, min_files=minimum)


def create_plan(db: Session, payload: dict, *, operator_email: str) -> CompactionJob:
    table = db.get(LakeTable, payload["table_id"])
    if table is None:
        raise not_found("lake_table", payload["table_id"])

    plan = build_plan_for_table(db, table, target_bytes=payload.get("target_bytes"), min_files=payload.get("min_files"))
    flow_lag = int(payload.get("flow_lag_seconds") if payload.get("flow_lag_seconds") is not None else table.flow_lag_seconds)
    window_start = payload.get("window_start") or datetime.combine(local_now().date(), datetime.min.time())
    window_end = payload.get("window_end") or (window_start.replace(hour=min(23, window_start.hour + 1)))
    if window_end <= window_start:
        raise AppError("VALIDATION", 422, {"field": "window_end", "reason": "window_end_must_be_after_start"})

    conflict = snapshot_verifier.check_window(
        job_start=window_start,
        job_end=window_end,
        flow_lag_seconds=flow_lag,
        stream_start=table.stream_window_start,
        stream_end=table.stream_window_end,
    )

    metrics = {key: value for key, value in plan.items() if key not in ("merge_groups", "rewrite_partitions", "skipped_partitions")}
    metrics["flow_lag_seconds"] = flow_lag
    job = CompactionJob(
        plan_no=next_plan_no(db),
        table_id=table.id,
        trigger=payload.get("trigger") or "manual",
        status="planned",
        target_bytes=plan["target_bytes"],
        min_files=plan["min_files"],
        flow_lag_seconds=flow_lag,
        window_start=window_start,
        window_end=window_end,
        operator_email=operator_email,
        metrics=metrics,
        merge_groups=plan["merge_groups"],
        rewrite_partitions=plan["rewrite_partitions"],
        skipped_partitions=plan["skipped_partitions"],
        conflict=conflict,
        review_status="pending",
    )
    db.add(job)
    db.flush()
    return job


# ---------------------------------------------------------------- 执行（算法 B）


def apply_merge(manifest: list[dict], groups: list[dict]) -> list[dict]:
    """把 merge_groups 落成 after manifest：同组多文件合成一个新文件，其余原样保留。"""
    grouped_paths: dict[str, dict] = {}
    for group in groups:
        for path in group.get("paths") or []:
            grouped_paths[path] = group
    merged_by_key: dict[tuple[str, int], dict] = {}
    after: list[dict] = []
    for item in manifest:
        group = grouped_paths.get(item["path"])
        if group is None:
            after.append(item)
            continue
        key = (str(item.get("partition_key") or ""), int(group.get("group_no") or 0))
        target = merged_by_key.get(key)
        if target is None:
            target = {
                "path": f"{item.get('partition_key')}/merged-{int(group.get('group_no') or 0):04d}.parquet",
                "partition_key": item.get("partition_key"),
                "kind": "data",
                "bytes": 0,
                "rows": 0,
                "checksum": 0,
            }
            merged_by_key[key] = target
            after.append(target)
        target["bytes"] = int(target["bytes"]) + int(item.get("bytes") or 0)
        target["rows"] = int(target["rows"]) + int(item.get("rows") or 0)
        target["checksum"] = (int(target["checksum"]) + int(item.get("checksum") or 0)) % (1 << 32)
    after.sort(key=lambda row: (str(row.get("partition_key") or ""), str(row.get("path") or "")))
    return after


def execute_job(db: Session, job: CompactionJob, *, actor_email: str) -> dict:
    if job.status == "executed":
        raise AppError("CONFLICT", 409, {"reason": "already_executed", "plan_no": job.plan_no})
    table = db.get(LakeTable, job.table_id)
    if table is None:
        raise not_found("lake_table", job.table_id)

    # 门禁 1：最近一次快照守恒失败 → 阻止执行
    latest_after = snapshot_service.latest_after(db, table.id)
    if latest_after is not None and latest_after.verdict == "lossy":
        job.status = "blocked"
        job.verify = {
            "verdict": "lossy",
            "reasons": (latest_after.verify or {}).get("reasons", ["rows_mismatch"]),
            "blocked_by": "snapshot_verify",
            "snapshot_no": latest_after.snapshot_no,
            "detail": latest_after.verify or {},
        }
        job.metrics = {**(job.metrics or {}), "blocked_reason": "snapshot_lossy"}
        db.flush()
        return {"ok": False, "blocked": True, "reason": "snapshot_lossy", "job": job, "table": table}

    # 门禁 2：与流读窗口相交 → 阻止执行
    window = snapshot_verifier.check_window(
        job_start=job.window_start,
        job_end=job.window_end,
        flow_lag_seconds=job.flow_lag_seconds,
        stream_start=table.stream_window_start,
        stream_end=table.stream_window_end,
    )
    job.conflict = window
    if window.get("conflict"):
        job.status = "blocked"
        job.verify = {"verdict": "unverifiable", "reasons": ["stream_conflict"], "blocked_by": "stream_window", "detail": window}
        db.flush()
        return {"ok": False, "blocked": True, "reason": "stream_conflict", "job": job, "table": table}

    # 执行模拟：按当前 manifest 重算 → 合并 → 落 before/after 快照 → 守恒校验
    plan = build_plan_for_table(db, table, target_bytes=job.target_bytes, min_files=job.min_files)
    manifest = [
        {key: value for key, value in item.items() if key != "partition_id"}
        for item in _current_manifest(db, table.id)
    ]
    after_manifest = apply_merge(manifest, plan["merge_groups"])
    pair = snapshot_service.record_pair(
        db,
        table_id=table.id,
        job_id=job.id,
        before_manifest=manifest,
        after_manifest=after_manifest,
    )
    verify = pair["verify"]
    job.status = "executed" if verify["verdict"] != "lossy" else "blocked"
    job.executed_at = utcnow()
    job.before_snapshot_id = pair["before"].id
    job.after_snapshot_id = pair["after"].id
    job.verify = verify
    job.merge_groups = plan["merge_groups"]
    job.rewrite_partitions = plan["rewrite_partitions"]
    job.skipped_partitions = plan["skipped_partitions"]
    job.metrics = {
        **{key: value for key, value in plan.items() if key not in ("merge_groups", "rewrite_partitions", "skipped_partitions")},
        "flow_lag_seconds": job.flow_lag_seconds,
        "executed_by": actor_email,
        "snapshot_seq": pair["seq_no"],
        "after_files": len(after_manifest),
        "verify_verdict": verify["verdict"],
    }
    db.flush()
    return {"ok": job.status == "executed", "blocked": False, "reason": None, "job": job, "table": table}


def _current_manifest(db: Session, table_id: int) -> list[dict]:
    rows = db.scalars(select(DataFile).where(DataFile.table_id == table_id).order_by(DataFile.partition_key, DataFile.file_no)).all()
    return [
        {
            "path": row.path,
            "partition_key": row.partition_key,
            "kind": row.kind,
            "bytes": row.bytes,
            "rows": row.rows,
            "checksum": row.checksum,
        }
        for row in rows
    ]


def update_window(db: Session, job: CompactionJob, *, window_start: datetime, window_end: datetime) -> dict:
    if window_end <= window_start:
        raise AppError("VALIDATION", 422, {"field": "window_end", "reason": "window_end_must_be_after_start"})
    table = db.get(LakeTable, job.table_id)
    job.window_start = window_start
    job.window_end = window_end
    job.conflict = snapshot_verifier.check_window(
        job_start=window_start,
        job_end=window_end,
        flow_lag_seconds=job.flow_lag_seconds,
        stream_start=table.stream_window_start if table else "00:00",
        stream_end=table.stream_window_end if table else "06:30",
    )
    if job.status == "blocked" and not job.conflict.get("conflict"):
        job.status = "planned"
        job.verify = {
            "verdict": "unverifiable",
            "reasons": ["window_rescheduled"],
            "blocked_by": None,
            "detail": job.conflict,
        }
    db.flush()
    return job.conflict


def review(db: Session, job: CompactionJob, *, status: str, note: str | None, reviewer: str) -> CompactionJob:
    job.review_status = status
    job.review_note = note
    job.reviewer = reviewer
    db.flush()
    return job


def window_check(db: Session, job: CompactionJob) -> dict:
    table = db.get(LakeTable, job.table_id)
    return snapshot_verifier.check_window(
        job_start=job.window_start,
        job_end=job.window_end,
        flow_lag_seconds=job.flow_lag_seconds,
        stream_start=table.stream_window_start if table else "00:00",
        stream_end=table.stream_window_end if table else "06:30",
    )

"""湖表服务：登记、查询、统计（分区/小文件/待 rewrite）。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import LAYER_LABELS, SMALL_FILE_BYTES, TABLE_FORMAT_LABELS
from src.models.data_file import DataFile
from src.models.lake_table import LakeTable
from src.models.partition import Partition
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc


def serialize(table: LakeTable, stats: dict | None = None) -> dict:
    payload = {
        "id": table.id,
        "code": table.code,
        "name": table.name,
        "layer": table.layer,
        "layer_label": LAYER_LABELS.get(table.layer, table.layer),
        "fmt": table.fmt,
        "fmt_label": TABLE_FORMAT_LABELS.get(table.fmt, table.fmt),
        "location": table.location,
        "partition_spec": table.partition_spec,
        "target_bytes": table.target_bytes,
        "target_mb": round(table.target_bytes / 1048576, 1),
        "min_files": table.min_files,
        "flow_lag_seconds": table.flow_lag_seconds,
        "stream_window_start": table.stream_window_start,
        "stream_window_end": table.stream_window_end,
        "owner": table.owner,
        "note": table.note,
        "enabled": table.enabled,
        "last_scanned_at": iso_utc(table.last_scanned_at),
        "created_at": iso_utc(table.created_at),
    }
    if stats is not None:
        payload["stats"] = stats
    return payload


def stats_by_table(db: Session) -> dict[int, dict]:
    rows = db.execute(
        select(
            Partition.table_id,
            func.count(Partition.id),
            func.coalesce(func.sum(Partition.file_count), 0),
            func.coalesce(func.sum(Partition.small_file_count), 0),
            func.coalesce(func.sum(Partition.total_bytes), 0),
            func.coalesce(func.sum(Partition.total_rows), 0),
            func.coalesce(func.sum(Partition.delete_file_count), 0),
        ).group_by(Partition.table_id)
    ).all()
    stats: dict[int, dict] = {}
    for table_id, parts, files, small, total_bytes, rows_total, delete_files in rows:
        stats[table_id] = {
            "partitions": int(parts or 0),
            "files": int(files or 0),
            "small_files": int(small or 0),
            "bytes": int(total_bytes or 0),
            "rows": int(rows_total or 0),
            "delete_files": int(delete_files or 0),
            "needs_rewrite_partitions": 0,
        }
    rewrite_rows = db.execute(
        select(Partition.table_id, func.count(Partition.id))
        .where(Partition.needs_rewrite.is_(True))
        .group_by(Partition.table_id)
    ).all()
    for table_id, count in rewrite_rows:
        stats.setdefault(table_id, {})["needs_rewrite_partitions"] = int(count or 0)
    return stats


def list_tables(
    db: Session,
    *,
    q: str | None = None,
    layer: str | None = None,
    enabled: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stmt = select(LakeTable)
    count_stmt = select(func.count()).select_from(LakeTable)
    if q:
        like = f"%{q.strip()}%"
        cond = LakeTable.name.ilike(like) | LakeTable.code.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if layer:
        stmt = stmt.where(LakeTable.layer == layer)
        count_stmt = count_stmt.where(LakeTable.layer == layer)
    if enabled is not None:
        stmt = stmt.where(LakeTable.enabled == enabled)
        count_stmt = count_stmt.where(LakeTable.enabled == enabled)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(LakeTable.id).limit(limit).offset(offset)).all()
    stats = stats_by_table(db)
    return {
        "items": [serialize(row, stats.get(row.id, _empty_stats())) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "small_file_threshold": SMALL_FILE_BYTES,
    }


def _empty_stats() -> dict:
    return {
        "partitions": 0,
        "files": 0,
        "small_files": 0,
        "bytes": 0,
        "rows": 0,
        "delete_files": 0,
        "needs_rewrite_partitions": 0,
    }


def get_table(db: Session, table_id: int) -> LakeTable:
    table = db.get(LakeTable, table_id)
    if table is None:
        raise not_found("lake_table", table_id)
    return table


def get_table_detail(db: Session, table_id: int) -> dict:
    table = get_table(db, table_id)
    stats = stats_by_table(db)
    return serialize(table, stats.get(table.id, _empty_stats()))


def create_table(db: Session, payload: dict) -> LakeTable:
    exists = db.scalar(select(LakeTable).where(LakeTable.code == payload["code"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"code": payload["code"]})
    table = LakeTable(
        code=payload["code"],
        name=payload["name"],
        layer=payload.get("layer") or "dwd",
        fmt=payload.get("fmt") or "iceberg",
        location=payload.get("location") or "s3://lg-lake/warehouse",
        partition_spec=payload.get("partition_spec") or "days(dt), hours(hour)",
        target_bytes=int(payload.get("target_bytes") or 134217728),
        min_files=int(payload.get("min_files") or 5),
        flow_lag_seconds=int(payload.get("flow_lag_seconds") or 900),
        stream_window_start=payload.get("stream_window_start") or "00:00",
        stream_window_end=payload.get("stream_window_end") or "06:30",
        owner=payload.get("owner") or "陆港物流 · 数据平台组",
        note=payload.get("note"),
        enabled=bool(payload.get("enabled", True)),
    )
    db.add(table)
    db.flush()
    return table


def update_table(db: Session, table: LakeTable, payload: dict) -> LakeTable:
    for field in (
        "name",
        "layer",
        "target_bytes",
        "min_files",
        "flow_lag_seconds",
        "stream_window_start",
        "stream_window_end",
        "note",
        "enabled",
    ):
        if field in payload and payload[field] is not None:
            setattr(table, field, payload[field])
    db.flush()
    return table


def table_manifest_files(db: Session, table_id: int) -> list[dict]:
    rows = db.scalars(select(DataFile).where(DataFile.table_id == table_id).order_by(DataFile.partition_key, DataFile.file_no)).all()
    return [
        {
            "path": row.path,
            "partition_key": row.partition_key,
            "partition_id": row.partition_id,
            "kind": row.kind,
            "bytes": row.bytes,
            "rows": row.rows,
            "checksum": row.checksum,
        }
        for row in rows
    ]

"""分区服务：按表 / 分层筛选，带小文件与 rewrite 标记。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import LAYER_LABELS, SMALL_FILE_BYTES
from src.models.lake_table import LakeTable
from src.models.partition import Partition
from src.utils.timeutil import iso_utc


def serialize(partition: Partition, table_code: str | None = None, table_name: str | None = None, layer: str | None = None) -> dict:
    avg_bytes = int(partition.total_bytes / partition.file_count) if partition.file_count else 0
    return {
        "id": partition.id,
        "table_id": partition.table_id,
        "table_code": table_code,
        "table_name": table_name,
        "layer": layer,
        "layer_label": LAYER_LABELS.get(layer or "", ""),
        "partition_key": partition.partition_key,
        "dt": partition.dt,
        "hour": partition.hour,
        "file_count": partition.file_count,
        "data_file_count": partition.data_file_count,
        "delete_file_count": partition.delete_file_count,
        "total_bytes": partition.total_bytes,
        "total_mb": round(partition.total_bytes / 1048576, 1),
        "total_rows": partition.total_rows,
        "small_file_count": partition.small_file_count,
        "avg_file_mb": round(avg_bytes / 1048576, 1),
        "needs_rewrite": partition.needs_rewrite,
        "scanned_at": iso_utc(partition.scanned_at),
    }


def list_partitions(
    db: Session,
    *,
    table_id: int | None = None,
    layer: str | None = None,
    needs_rewrite: bool | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(Partition, LakeTable).join(LakeTable, LakeTable.id == Partition.table_id)
    count_stmt = select(func.count()).select_from(Partition).join(LakeTable, LakeTable.id == Partition.table_id)
    if table_id:
        stmt = stmt.where(Partition.table_id == table_id)
        count_stmt = count_stmt.where(Partition.table_id == table_id)
    if layer:
        stmt = stmt.where(LakeTable.layer == layer)
        count_stmt = count_stmt.where(LakeTable.layer == layer)
    if needs_rewrite is not None:
        stmt = stmt.where(Partition.needs_rewrite.is_(needs_rewrite))
        count_stmt = count_stmt.where(Partition.needs_rewrite.is_(needs_rewrite))
    if q:
        like = f"%{q.strip()}%"
        cond = Partition.partition_key.ilike(like) | LakeTable.name.ilike(like) | LakeTable.code.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = db.scalar(count_stmt) or 0
    rows = db.execute(stmt.order_by(Partition.table_id, Partition.partition_key).limit(limit).offset(offset)).all()
    return {
        "items": [serialize(partition, table.code, table.name, table.layer) for partition, table in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "small_file_threshold": SMALL_FILE_BYTES,
    }


def partition_stats(db: Session, table_id: int | None = None) -> dict:
    stmt = select(
        func.count(Partition.id),
        func.coalesce(func.sum(Partition.file_count), 0),
        func.coalesce(func.sum(Partition.small_file_count), 0),
        func.coalesce(func.sum(Partition.total_bytes), 0),
        func.coalesce(func.sum(Partition.delete_file_count), 0),
        func.coalesce(func.sum(Partition.total_rows), 0),
    )
    if table_id:
        stmt = stmt.where(Partition.table_id == table_id)
    partitions, files, small, total_bytes, delete_files, rows = db.execute(stmt).one()
    rewrite_stmt = select(func.count()).select_from(Partition).where(Partition.needs_rewrite.is_(True))
    if table_id:
        rewrite_stmt = rewrite_stmt.where(Partition.table_id == table_id)
    rewrite = db.scalar(rewrite_stmt) or 0
    return {
        "partitions": int(partitions or 0),
        "files": int(files or 0),
        "small_files": int(small or 0),
        "bytes": int(total_bytes or 0),
        "delete_files": int(delete_files or 0),
        "rows": int(rows or 0),
        "needs_rewrite_partitions": int(rewrite),
    }

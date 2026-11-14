"""文件清单服务：manifest 明细查询 + 扫描重算分区聚合。"""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from src.constants.enums import FILE_KIND_LABELS, SMALL_FILE_BYTES
from src.models.data_file import DataFile
from src.models.lake_table import LakeTable
from src.models.partition import Partition
from src.utils.errors import not_found
from src.utils.timeutil import iso_utc, utcnow


def serialize(row: DataFile, table_code: str | None = None, table_name: str | None = None) -> dict:
    return {
        "id": row.id,
        "table_id": row.table_id,
        "table_code": table_code,
        "table_name": table_name,
        "partition_id": row.partition_id,
        "partition_key": row.partition_key,
        "path": row.path,
        "kind": row.kind,
        "kind_label": FILE_KIND_LABELS.get(row.kind, row.kind),
        "bytes": row.bytes,
        "mb": round(row.bytes / 1048576, 2),
        "rows": row.rows,
        "checksum": row.checksum,
        "file_no": row.file_no,
        "is_small": row.bytes < SMALL_FILE_BYTES,
        "committed_at": iso_utc(row.committed_at),
    }


def list_files(
    db: Session,
    *,
    table_id: int | None = None,
    partition_id: int | None = None,
    kind: str | None = None,
    q: str | None = None,
    small_only: bool = False,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    stmt = select(DataFile, LakeTable).join(LakeTable, LakeTable.id == DataFile.table_id)
    count_stmt = select(func.count()).select_from(DataFile).join(LakeTable, LakeTable.id == DataFile.table_id)
    conditions = []
    if table_id:
        conditions.append(DataFile.table_id == table_id)
    if partition_id:
        conditions.append(DataFile.partition_id == partition_id)
    if kind:
        conditions.append(DataFile.kind == kind)
    if small_only:
        conditions.append(DataFile.bytes < SMALL_FILE_BYTES)
    if q:
        like = f"%{q.strip()}%"
        conditions.append(DataFile.path.ilike(like) | DataFile.partition_key.ilike(like) | LakeTable.name.ilike(like))
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(DataFile.table_id, DataFile.partition_key, DataFile.file_no).limit(limit).offset(offset)
    ).all()
    return {
        "items": [serialize(row, table.code, table.name) for row, table in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "small_file_threshold": SMALL_FILE_BYTES,
    }


def file_stats(db: Session, table_id: int | None = None) -> dict:
    stmt = select(
        func.count(DataFile.id),
        func.coalesce(func.sum(DataFile.bytes), 0),
        func.coalesce(func.sum(DataFile.rows), 0),
        func.coalesce(func.sum(case((DataFile.kind == "delete", 1), else_=0)), 0),
        func.coalesce(func.sum(case((DataFile.bytes < SMALL_FILE_BYTES, 1), else_=0)), 0),
    )
    if table_id:
        stmt = stmt.where(DataFile.table_id == table_id)
    files, total_bytes, rows, delete_files, small_files = db.execute(stmt).one()
    return {
        "files": int(files or 0),
        "bytes": int(total_bytes or 0),
        "rows": int(rows or 0),
        "delete_files": int(delete_files or 0),
        "small_files": int(small_files or 0),
        "small_file_threshold": SMALL_FILE_BYTES,
    }


def scan(db: Session, table_id: int | None = None) -> dict:
    """从 data_files 重算每个分区的聚合，并刷新 last_scanned_at。扫描模块的落地点。"""
    tables_stmt = select(LakeTable)
    if table_id:
        tables_stmt = tables_stmt.where(LakeTable.id == table_id)
    tables = db.scalars(tables_stmt).all()
    if table_id and not tables:
        raise not_found("lake_table", table_id)
    scanned_partitions = 0
    scanned_files = 0
    for table in tables:
        partitions = db.scalars(select(Partition).where(Partition.table_id == table.id)).all()
        for partition in partitions:
            files = db.scalars(select(DataFile).where(DataFile.partition_id == partition.id)).all()
            data_files = [item for item in files if item.kind == "data"]
            delete_files = [item for item in files if item.kind == "delete"]
            partition.file_count = len(files)
            partition.data_file_count = len(data_files)
            partition.delete_file_count = len(delete_files)
            partition.total_bytes = sum(item.bytes for item in files)
            partition.total_rows = sum(item.rows for item in data_files)
            partition.small_file_count = sum(1 for item in files if item.bytes < SMALL_FILE_BYTES)
            partition.needs_rewrite = bool(delete_files)
            partition.scanned_at = utcnow()
            scanned_partitions += 1
            scanned_files += len(files)
        table.last_scanned_at = utcnow()
    db.flush()
    return {"tables": len(tables), "partitions": scanned_partitions, "files": scanned_files}

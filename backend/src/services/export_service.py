"""导出服务：合并计划清单 / 快照校验清单（UTF-8 BOM CSV）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    JOB_STATUS_LABELS,
    LAYER_LABELS,
    REVIEW_STATUS_LABELS,
    VERDICT_LABELS,
)
from src.models.compaction_job import CompactionJob
from src.models.lake_table import LakeTable
from src.models.snapshot import Snapshot
from src.utils.csv_export import to_csv


def _stamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def plans_csv(db: Session, *, table_id: int | None = None) -> bytes:
    stmt = select(CompactionJob)
    if table_id:
        stmt = stmt.where(CompactionJob.table_id == table_id)
    jobs = db.scalars(stmt.order_by(CompactionJob.id)).all()
    tables = {table.id: table for table in db.scalars(select(LakeTable)).all()}
    headers = [
        "计划编号",
        "湖表",
        "分层",
        "目标文件MB",
        "最小文件数",
        "状态",
        "合并组数",
        "合并前文件数",
        "合并后文件数",
        "减少文件数",
        "IO节省比例",
        "平均装箱填充",
        "合并前字节",
        "待rewrite分区",
        "冲突窗口",
        "建议窗口",
        "复核状态",
        "执行人",
        "创建时间",
        "执行时间",
    ]
    rows = []
    for job in jobs:
        table = tables.get(job.table_id)
        metrics = job.metrics or {}
        conflict = job.conflict or {}
        suggestion = conflict.get("suggested_window") or {}
        rows.append(
            [
                job.plan_no,
                f"{table.code} {table.name}" if table else "",
                LAYER_LABELS.get(table.layer, table.layer) if table else "",
                round(job.target_bytes / 1048576, 1),
                job.min_files,
                JOB_STATUS_LABELS.get(job.status, job.status),
                len(job.merge_groups or []),
                metrics.get("files_before", ""),
                metrics.get("expected_files_after", ""),
                metrics.get("files_reduced", ""),
                metrics.get("io_saved_ratio", ""),
                metrics.get("avg_fill_ratio", ""),
                metrics.get("bytes_before", ""),
                len(job.rewrite_partitions or []),
                "是" if conflict.get("conflict") else "否",
                f"{suggestion.get('start', '')}~{suggestion.get('end', '')}" if suggestion else "",
                REVIEW_STATUS_LABELS.get(job.review_status, job.review_status),
                job.operator_email,
                _stamp(job.created_at),
                _stamp(job.executed_at),
            ]
        )
    return to_csv(headers, rows)


def snapshots_csv(db: Session, *, table_id: int | None = None) -> bytes:
    stmt = select(Snapshot)
    if table_id:
        stmt = stmt.where(Snapshot.table_id == table_id)
    snapshots = db.scalars(stmt.order_by(Snapshot.table_id, Snapshot.seq_no, Snapshot.label)).all()
    tables = {table.id: table for table in db.scalars(select(LakeTable)).all()}
    headers = [
        "湖表",
        "快照",
        "序号",
        "阶段",
        "文件数",
        "delete文件数",
        "行数",
        "校验和",
        "字节",
        "守恒结论",
        "原因",
        "提交时间",
    ]
    rows = []
    for snapshot in snapshots:
        table = tables.get(snapshot.table_id)
        verify = snapshot.verify or {}
        rows.append(
            [
                f"{table.code} {table.name}" if table else "",
                snapshot.snapshot_no,
                snapshot.seq_no,
                "合并前" if snapshot.label == "before" else "合并后",
                snapshot.data_file_count + snapshot.delete_file_count,
                snapshot.delete_file_count,
                snapshot.total_rows,
                snapshot.checksum,
                snapshot.bytes,
                VERDICT_LABELS.get(snapshot.verdict or "", "未校验"),
                ",".join(verify.get("reasons") or []),
                _stamp(snapshot.committed_at),
            ]
        )
    return to_csv(headers, rows)

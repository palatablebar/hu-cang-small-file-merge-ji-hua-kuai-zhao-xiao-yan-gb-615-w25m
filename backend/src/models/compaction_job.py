"""合并计划 / 执行作业：算法 A 的结果 + 冲突窗口 + 复核结论。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class CompactionJob(Base):
    __tablename__ = "compaction_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("lake_tables.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)
    target_bytes: Mapped[int] = mapped_column(Integer, default=134217728)
    min_files: Mapped[int] = mapped_column(Integer, default=5)
    flow_lag_seconds: Mapped[int] = mapped_column(Integer, default=900)
    window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    operator_email: Mapped[str] = mapped_column(String(160), default="system")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    merge_groups: Mapped[list] = mapped_column(JSON, default=list)
    rewrite_partitions: Mapped[list] = mapped_column(JSON, default=list)
    skipped_partitions: Mapped[list] = mapped_column(JSON, default=list)
    conflict: Mapped[dict] = mapped_column(JSON, default=dict)
    before_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verify: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

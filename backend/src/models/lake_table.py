"""湖表：Iceberg 风格表登记（分区规格、目标文件大小、流读窗口）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class LakeTable(Base):
    __tablename__ = "lake_tables"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    layer: Mapped[str] = mapped_column(String(12), default="dwd", index=True)
    fmt: Mapped[str] = mapped_column(String(16), default="iceberg")
    location: Mapped[str] = mapped_column(String(255), default="s3://lg-lake/warehouse")
    partition_spec: Mapped[str] = mapped_column(String(120), default="days(dt), hours(hour)")
    target_bytes: Mapped[int] = mapped_column(Integer, default=134217728)
    min_files: Mapped[int] = mapped_column(Integer, default=5)
    flow_lag_seconds: Mapped[int] = mapped_column(Integer, default=900)
    stream_window_start: Mapped[str] = mapped_column(String(5), default="00:00")
    stream_window_end: Mapped[str] = mapped_column(String(5), default="06:30")
    owner: Mapped[str] = mapped_column(String(80), default="陆港物流 · 数据平台组")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

"""表分区：dt=YYYY-MM-DD/hour=HH，一个分区一个目录。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Partition(Base):
    __tablename__ = "partitions"
    __table_args__ = (UniqueConstraint("table_id", "partition_key", name="uq_partitions_table_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("lake_tables.id", ondelete="CASCADE"), index=True)
    partition_key: Mapped[str] = mapped_column(String(80), index=True)
    dt: Mapped[str] = mapped_column(String(10), index=True)
    hour: Mapped[str] = mapped_column(String(2), default="00")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    data_file_count: Mapped[int] = mapped_column(Integer, default=0)
    delete_file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    total_rows: Mapped[int] = mapped_column(BigInteger, default=0)
    small_file_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_rewrite: Mapped[bool] = mapped_column(Boolean, default=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

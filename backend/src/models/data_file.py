"""manifest 里的一条文件记录：data 或 delete（position/equality delete）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class DataFile(Base):
    __tablename__ = "data_files"
    __table_args__ = (UniqueConstraint("table_id", "path", name="uq_data_files_table_path"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("lake_tables.id", ondelete="CASCADE"), index=True)
    partition_id: Mapped[int] = mapped_column(ForeignKey("partitions.id", ondelete="CASCADE"), index=True)
    partition_key: Mapped[str] = mapped_column(String(80), index=True)
    path: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(10), default="data", index=True)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[int] = mapped_column(BigInteger, default=0)
    file_no: Mapped[int] = mapped_column(Integer, default=0)
    committed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

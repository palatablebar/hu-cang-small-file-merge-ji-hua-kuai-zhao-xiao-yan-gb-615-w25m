"""快照：一次提交的 manifest 摘要（before / after 成对用于守恒校验）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON

from src.models import Base
from src.utils.timeutil import utcnow


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint("table_id", "label", "seq_no", name="uq_snapshots_table_label_seq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("lake_tables.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(10), default="before", index=True)
    seq_no: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_no: Mapped[str] = mapped_column(String(40), default="")
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    manifest: Mapped[list] = mapped_column(JSON, default=list)
    data_file_count: Mapped[int] = mapped_column(Integer, default=0)
    delete_file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    verify: Mapped[dict] = mapped_column(JSON, default=dict)
    committed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

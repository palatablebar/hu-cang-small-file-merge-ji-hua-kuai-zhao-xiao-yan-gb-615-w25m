from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PlanIn(BaseModel):
    table_id: int = Field(ge=1)
    target_bytes: int | None = Field(default=None, ge=1048576, le=1073741824)
    min_files: int | None = Field(default=None, ge=2, le=100)
    flow_lag_seconds: int | None = Field(default=None, ge=0, le=7200)
    window_start: datetime | None = None
    window_end: datetime | None = None
    trigger: Literal["manual", "schedule", "backfill"] = "manual"


class PlanWindowIn(BaseModel):
    window_start: datetime
    window_end: datetime


class ReviewIn(BaseModel):
    status: Literal["pending", "confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)

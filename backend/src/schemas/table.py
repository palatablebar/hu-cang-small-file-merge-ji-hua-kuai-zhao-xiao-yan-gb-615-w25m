from __future__ import annotations

from pydantic import BaseModel, Field

LAYERS = ("ods", "dwd", "dws", "dim", "ads")
FORMATS = ("iceberg", "hudi", "paimon")


class TableIn(BaseModel):
    code: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=120)
    layer: str = "dwd"
    fmt: str = "iceberg"
    location: str | None = Field(default=None, max_length=255)
    partition_spec: str | None = Field(default=None, max_length=120)
    target_bytes: int = Field(default=134217728, ge=1048576, le=1073741824)
    min_files: int = Field(default=5, ge=2, le=100)
    flow_lag_seconds: int = Field(default=900, ge=0, le=7200)
    stream_window_start: str = Field(default="00:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    stream_window_end: str = Field(default="06:30", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    owner: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=1000)
    enabled: bool = True


class TablePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    layer: str | None = None
    target_bytes: int | None = Field(default=None, ge=1048576, le=1073741824)
    min_files: int | None = Field(default=None, ge=2, le=100)
    flow_lag_seconds: int | None = Field(default=None, ge=0, le=7200)
    stream_window_start: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    stream_window_end: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    note: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None

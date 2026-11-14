from __future__ import annotations

from pydantic import BaseModel, Field


class VerifyIn(BaseModel):
    before_id: int = Field(ge=1)
    after_id: int = Field(ge=1)

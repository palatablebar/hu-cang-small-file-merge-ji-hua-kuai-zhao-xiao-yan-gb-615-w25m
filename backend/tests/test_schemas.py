"""参数校验单测：非法参数必须被 pydantic 拦下（对应 HTTP 422）。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.compaction import PlanIn, PlanWindowIn, ReviewIn
from src.schemas.snapshot import VerifyIn
from src.schemas.table import TableIn, TablePatch


def test_plan_requires_positive_table_id():
    with pytest.raises(ValidationError):
        PlanIn(table_id=0)


def test_plan_target_bytes_bounds():
    with pytest.raises(ValidationError):
        PlanIn(table_id=1, target_bytes=100)
    with pytest.raises(ValidationError):
        PlanIn(table_id=1, target_bytes=8 * 1024 * 1024 * 1024)
    assert PlanIn(table_id=1, target_bytes=64 * 1024 * 1024).target_bytes == 67108864


def test_plan_min_files_bounds():
    with pytest.raises(ValidationError):
        PlanIn(table_id=1, min_files=1)


def test_table_code_pattern():
    with pytest.raises(ValidationError):
        TableIn(code="Dwd-Order", name="订单明细")
    with pytest.raises(ValidationError):
        TableIn(code="dwd_order_detail", name="x")
    assert TableIn(code="dwd_order_detail", name="订单明细").layer == "dwd"


def test_table_stream_window_pattern():
    with pytest.raises(ValidationError):
        TablePatch(stream_window_start="25:00")


def test_review_status_is_literal():
    with pytest.raises(ValidationError):
        ReviewIn(status="maybe")
    assert ReviewIn(status="confirmed").status == "confirmed"


def test_window_must_be_parsable():
    with pytest.raises(ValidationError):
        PlanWindowIn(window_start="not-a-date", window_end="2026-11-13T10:00")


def test_verify_ids_must_be_positive():
    with pytest.raises(ValidationError):
        VerifyIn(before_id=0, after_id=1)

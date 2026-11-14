"""算法 B｜快照 diff / 守恒校验 / 冲突窗口。"""
from __future__ import annotations

from datetime import datetime

import pytest

from src.services import snapshot_verifier as sv


def _f(path: str, rows: int, checksum: int, kind: str = "data", partition: str = "dt=1/hour=00", size: int = 10) -> dict:
    return {"path": path, "partition_key": partition, "kind": kind, "bytes": size, "rows": rows, "checksum": checksum}


def test_consistent_after_merge():
    before = [_f("a/1.parquet", 100, 7), _f("a/2.parquet", 200, 11)]
    after = [_f("a/merged-0001.parquet", 300, 18)]
    result = sv.verify_manifests(before, after)

    assert result["verdict"] == "consistent"
    assert result["reasons"] == ["rows_and_checksum_preserved"]
    assert result["rows_before"] == 300 and result["rows_after"] == 300
    assert result["checksum_before"] == result["checksum_after"] == 18
    assert result["counts"] == {"added": 1, "removed": 2, "rewritten": 1, "unchanged": 0}
    assert result["rewritten"][0]["files_in"] == 2
    assert result["rewritten"][0]["files_out"] == 1


def test_three_rows_missing_is_lossy_and_localized():
    before = [_f("a/1.parquet", 100, 7), _f("a/2.parquet", 200, 11)]
    after = [_f("a/merged-0001.parquet", 297, 18)]
    result = sv.verify_manifests(before, after)

    assert result["verdict"] == "lossy"
    assert "rows_mismatch" in result["reasons"]
    assert result["rows_delta"] == -3
    assert result["rows_conserved"] is False
    # 校验和按合并结果写入，所以只有行数不守恒
    assert result["checksum_conserved"] is True
    assert result["lossy_partitions"][0]["rows_delta"] == -3


def test_checksum_mismatch_is_lossy():
    before = [_f("a/1.parquet", 100, 7), _f("a/2.parquet", 100, 11)]
    after = [_f("a/merged-0001.parquet", 200, 99)]
    result = sv.verify_manifests(before, after)
    assert result["verdict"] == "lossy"
    assert result["reasons"] == ["checksum_mismatch"]


def test_missing_checksum_is_unverifiable():
    before = [_f("a/1.parquet", 100, 7)]
    after = [_f("a/merged-0001.parquet", 100, None)]
    result = sv.verify_manifests(before, after)
    assert result["verdict"] == "unverifiable"
    assert result["reasons"] == ["checksum_missing"]


def test_empty_manifest_is_unverifiable():
    assert sv.verify_manifests([], [_f("a/1.parquet", 1, 1)])["verdict"] == "unverifiable"
    assert sv.verify_manifests([_f("a/1.parquet", 1, 1)], [])["verdict"] == "unverifiable"


def test_delete_files_use_xor_and_stay_out_of_rows():
    before = [_f("a/1.parquet", 100, 5), _f("a/del.parquet", 0, 3, kind="delete")]
    # rewrite 后 delete 收敛掉，数据文件行数不变
    after = [_f("a/1.parquet", 100, 5)]
    result = sv.verify_manifests(before, after)
    assert result["rows_before"] == 100
    assert result["rows_conserved"] is True
    assert result["checksum_before"] == sv.combine_checksum(before)
    assert result["verdict"] == "lossy"  # delete 文件消失导致校验和变化，需要显式 rewrite 记录


def test_verify_is_deterministic():
    before = [_f(f"a/{i}.parquet", 100 + i, i * 3) for i in range(5)]
    after = [_f("a/merged-0001.parquet", sum(100 + i for i in range(5)), sum(i * 3 for i in range(5)))]
    assert sv.verify_manifests(before, after) == sv.verify_manifests(before, after)


def test_window_conflict_and_suggestion():
    window = sv.check_window(
        job_start=datetime(2026, 11, 13, 2, 0),
        job_end=datetime(2026, 11, 13, 3, 0),
        flow_lag_seconds=900,
        stream_start="00:00",
        stream_end="06:30",
    )
    assert window["conflict"] is True
    assert window["overlap_minutes"] == 75
    assert window["guard_start"] == "2026-11-13T01:45"
    assert window["suggested_window"] == {"start": "2026-11-13T06:45", "end": "2026-11-13T07:45"}


def test_window_outside_stream_is_clean():
    window = sv.check_window(
        job_start=datetime(2026, 11, 13, 20, 0),
        job_end=datetime(2026, 11, 13, 21, 0),
        flow_lag_seconds=900,
        stream_start="00:00",
        stream_end="06:30",
    )
    assert window["conflict"] is False
    assert window["overlap_minutes"] == 0
    assert window["reason"] == "outside_stream_window"


def test_window_missing_arguments():
    window = sv.check_window(job_start=None, job_end=None, flow_lag_seconds=0)
    assert window["conflict"] is False
    assert window["reason"] == "window_missing"

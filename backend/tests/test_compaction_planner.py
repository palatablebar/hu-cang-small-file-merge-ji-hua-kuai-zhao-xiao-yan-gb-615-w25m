"""算法 A｜合并计划：装箱、边界、确定性。"""
from __future__ import annotations

from math import ceil

import pytest

from src.services import compaction_planner

TARGET = 128 * 1024 * 1024
MIB = 1024 * 1024


def _file(path: str, mib: float, kind: str = "data", rows: int = 1000, checksum: int = 7) -> dict:
    return {"path": path, "kind": kind, "bytes": int(mib * MIB), "rows": rows, "checksum": checksum}


def _partition(key: str, files: list[dict], layer: str = "dwd") -> dict:
    return {"partition_key": key, "layer": layer, "files": files}


def test_acceptance_partition_packs_into_25_groups():
    """验收分区：25 个 0.55×target + 23 个 0.45×target = 48 文件，FFD 恰好 25 桶。"""
    anchor = int(TARGET * 0.55)
    filler = TARGET - anchor
    files = [
        {"path": f"a/{i}.parquet", "kind": "data", "bytes": anchor, "rows": 1000 + i, "checksum": i}
        for i in range(25)
    ]
    files += [
        {"path": f"f/{i}.parquet", "kind": "data", "bytes": filler, "rows": 900 + i, "checksum": 100 + i}
        for i in range(23)
    ]
    total = sum(item["bytes"] for item in files)
    result = compaction_planner.build_plan([_partition("dt=2026-11-13/hour=00", files)])

    assert result["files_before"] == 48
    assert result["bytes_before"] == total
    assert result["groups_total"] == 25
    assert result["expected_files_after"] == 25
    assert result["io_saved_ratio"] == round((48 - 25) / 48, 4)
    assert result["bins_lower_bound"] == ceil(total / TARGET) == 25
    assert result["ffd_over_lower_bound"] == 0
    # 每个桶不超容量，且文件总数守恒
    assert all(group["bytes"] <= TARGET for group in result["merge_groups"])
    assert sum(group["files"] for group in result["merge_groups"]) == 48
    # 行数守恒（按组合并前后）
    assert sum(group["rows"] for group in result["merge_groups"]) == sum(item["rows"] for item in files)


def test_delete_partition_requires_rewrite_first():
    files = [_file(f"d/{i}", 4) for i in range(10)]
    files.append(_file("d/del.pos-del", 0.5, kind="delete", rows=0, checksum=99))
    result = compaction_planner.build_plan([_partition("dt=2026-11-13/hour=03", files)])

    assert result["merge_groups"] == []
    assert len(result["rewrite_partitions"]) == 1
    entry = result["rewrite_partitions"][0]
    assert entry["delete_files"] == 1
    assert entry["data_files"] == 10
    # rewrite 分区本轮不动文件，expected_files_after 保持原数
    assert result["expected_files_after"] == 11
    assert result["files_reduced"] == 0


def test_oversized_file_not_packed():
    files = [_file(f"o/{i}", 10) for i in range(8)]
    files.append(_file("o/big", 160))
    result = compaction_planner.build_plan([_partition("dt=2026-11-13/hour=01", files)])

    assert result["expected_files_after"] == result["groups_total"] + 1
    packed_paths = {path for group in result["merge_groups"] for path in group["paths"]}
    assert "o/big" not in packed_paths
    assert sum(group["files"] for group in result["merge_groups"]) == 8


def test_below_min_files_partition_is_skipped():
    files = [_file(f"s/{i}", 6) for i in range(3)]
    result = compaction_planner.build_plan([_partition("dt=2026-11-13/hour=02", files)], min_files=5)

    assert result["merge_groups"] == []
    assert result["skipped_partitions"][0]["reason"] == compaction_planner.SKIP_BELOW_MIN
    assert result["expected_files_after"] == 3
    assert result["io_saved_ratio"] == 0.0


def test_all_oversized_partition_is_skipped():
    files = [_file(f"x/{i}", 200) for i in range(6)]
    result = compaction_planner.build_plan([_partition("dt=2026-11-13/hour=04", files)])
    assert result["merge_groups"] == []
    assert result["skipped_partitions"][0]["reason"] == compaction_planner.SKIP_ALL_OVERSIZED


def test_empty_input_returns_zero_metrics():
    result = compaction_planner.build_plan([])
    assert result["files_before"] == 0
    assert result["groups_total"] == 0
    assert result["expected_files_after"] == 0
    assert result["io_saved_ratio"] == 0.0
    assert result["avg_fill_ratio"] == 0.0


def test_plan_is_deterministic_and_input_order_independent():
    files = [_file(f"p/{i}", 3 + (i % 9), rows=100 + i, checksum=i) for i in range(20)]
    first = compaction_planner.build_plan([_partition("dt=2026-11-13/hour=05", files)])
    second = compaction_planner.build_plan([_partition("dt=2026-11-13/hour=05", list(reversed(files)))])
    assert first == second


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        compaction_planner.build_plan([], target_bytes=0)
    with pytest.raises(ValueError):
        compaction_planner.build_plan([], min_files=0)

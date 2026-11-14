"""算法 A｜合并计划（First-Fit-Decreasing 装箱）。

纯函数、无副作用、无数据库依赖，便于单测与复算。

口径：
- 目标文件大小 target_bytes（默认 128 MiB），每分区最小文件数 min_files（默认 5）。
- 单文件 bytes > target_bytes 不参与合并（保持原样）。
- 分区内 data 文件按 (bytes 降序, path 升序) 排序后做 FFD 装箱，桶容量 = target_bytes。
- 含 delete 文件（position/equality delete）的分区必须先 rewrite 再 merge：
  本轮不装箱，标记 needs_rewrite，文件数按原样计入 expected_files_after。
- expected_files_after = Σ(各分区合并后文件数)：
    已合并分区 = 装箱桶数 + 超大文件数；rewrite / 跳过分区 = 原文件数。
- io_saved_ratio = (files_before - expected_files_after) / files_before（文件数降幅，收益口径）。
- bins_lower_bound = Σ ceil(分区总字节 / target_bytes)，用于对照 FFD 与理论下界。
"""
from __future__ import annotations

from math import ceil

DEFAULT_TARGET_BYTES = 128 * 1024 * 1024
DEFAULT_MIN_FILES = 5

SKIP_BELOW_MIN = "below_min_files"
SKIP_NO_DATA = "no_data_files"
SKIP_ALL_OVERSIZED = "all_oversized"


def _sorted_files(files: list[dict]) -> list[dict]:
    return sorted(files, key=lambda item: (-int(item.get("bytes") or 0), str(item.get("path") or "")))


def first_fit_decreasing(items: list[dict], capacity: int) -> list[dict]:
    """items 必须已按 bytes 降序排序；返回 [{used, items:[...]}]，桶按首次开启顺序。"""
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    bins: list[dict] = []
    for item in items:
        size = int(item.get("bytes") or 0)
        for bucket in bins:
            if bucket["used"] + size <= capacity:
                bucket["used"] += size
                bucket["items"].append(item)
                break
        else:
            bins.append({"used": size, "items": [item]})
    return bins


def _group_from_bin(partition_key: str, layer: str, bucket: dict, group_no: int, target_bytes: int) -> dict:
    files = bucket["items"]
    rows = sum(int(item.get("rows") or 0) for item in files)
    checksum = sum(int(item.get("checksum") or 0) for item in files) % (1 << 32)
    return {
        "partition_key": partition_key,
        "layer": layer,
        "group_no": group_no,
        "files": len(files),
        "bytes": bucket["used"],
        "rows": rows,
        "checksum": checksum,
        "fill_ratio": round(bucket["used"] / target_bytes, 4),
        "paths": [item.get("path") for item in files],
    }


def build_plan(
    partitions: list[dict],
    *,
    target_bytes: int = DEFAULT_TARGET_BYTES,
    min_files: int = DEFAULT_MIN_FILES,
) -> dict:
    """对一组分区生成合并计划。

    partitions: [{"partition_key", "layer", "files": [{"path","kind","bytes","rows","checksum"}]}]
    """
    target_bytes = int(target_bytes)
    min_files = int(min_files)
    if target_bytes <= 0:
        raise ValueError("target_bytes must be positive")
    if min_files < 1:
        raise ValueError("min_files must be >= 1")

    merge_groups: list[dict] = []
    rewrite_partitions: list[dict] = []
    skipped_partitions: list[dict] = []

    files_before = 0
    bytes_before = 0
    rows_before = 0
    expected_files_after = 0
    bins_lower_bound = 0
    partitions_merged = 0
    fill_ratios: list[float] = []
    rewritten_delete_bytes = 0

    for partition in sorted(partitions, key=lambda item: str(item.get("partition_key") or "")):
        key = str(partition.get("partition_key") or "")
        layer = str(partition.get("layer") or "")
        files = list(partition.get("files") or [])
        data_files = [item for item in files if (item.get("kind") or "data") == "data"]
        delete_files = [item for item in files if (item.get("kind") or "data") == "delete"]

        part_bytes = sum(int(item.get("bytes") or 0) for item in files)
        part_rows = sum(int(item.get("rows") or 0) for item in data_files)
        files_before += len(files)
        bytes_before += part_bytes
        rows_before += part_rows

        # 含 delete 文件：必须先 rewrite 再 merge，本轮不动
        if delete_files:
            deleted_bytes = sum(int(item.get("bytes") or 0) for item in delete_files)
            rewritten_delete_bytes += deleted_bytes
            rewrite_partitions.append(
                {
                    "partition_key": key,
                    "layer": layer,
                    "delete_files": len(delete_files),
                    "data_files": len(data_files),
                    "delete_bytes": deleted_bytes,
                    "data_bytes": part_bytes - deleted_bytes,
                    "rows": part_rows,
                    "reason": "存在 delete 文件，必须先 rewrite 收敛删除再合并数据文件",
                }
            )
            expected_files_after += len(files)
            continue

        if len(data_files) < min_files:
            skipped_partitions.append(
                {
                    "partition_key": key,
                    "layer": layer,
                    "files": len(data_files),
                    "bytes": part_bytes,
                    "reason": SKIP_BELOW_MIN,
                    "min_files": min_files,
                }
            )
            expected_files_after += len(data_files)
            continue

        if not data_files:
            skipped_partitions.append(
                {"partition_key": key, "layer": layer, "files": 0, "bytes": part_bytes, "reason": SKIP_NO_DATA}
            )
            continue

        eligible = [item for item in data_files if int(item.get("bytes") or 0) <= target_bytes]
        oversized = [item for item in data_files if int(item.get("bytes") or 0) > target_bytes]

        if len(eligible) < min_files:
            skipped_partitions.append(
                {
                    "partition_key": key,
                    "layer": layer,
                    "files": len(data_files),
                    "bytes": part_bytes,
                    "reason": SKIP_ALL_OVERSIZED,
                    "eligible": len(eligible),
                    "oversized": len(oversized),
                }
            )
            expected_files_after += len(data_files)
            continue

        buckets = first_fit_decreasing(_sorted_files(eligible), target_bytes)
        partitions_merged += 1
        bins_lower_bound += ceil(sum(int(item.get("bytes") or 0) for item in eligible) / target_bytes)
        for index, bucket in enumerate(buckets, start=1):
            group = _group_from_bin(key, layer, bucket, index, target_bytes)
            fill_ratios.append(group["fill_ratio"])
            merge_groups.append(group)
        expected_files_after += len(buckets) + len(oversized)

    files_reduced = files_before - expected_files_after
    return {
        "target_bytes": target_bytes,
        "min_files": min_files,
        "partitions_scanned": len(partitions),
        "partitions_merged": partitions_merged,
        "files_before": files_before,
        "bytes_before": bytes_before,
        "rows_before": rows_before,
        "merge_groups": merge_groups,
        "groups_total": len(merge_groups),
        "rewrite_partitions": rewrite_partitions,
        "skipped_partitions": skipped_partitions,
        "expected_files_after": expected_files_after,
        "files_reduced": files_reduced,
        "io_saved_ratio": round(files_reduced / files_before, 4) if files_before else 0.0,
        "bins_lower_bound": bins_lower_bound,
        "ffd_over_lower_bound": len(merge_groups) - bins_lower_bound,
        "avg_fill_ratio": round(sum(fill_ratios) / len(fill_ratios), 4) if fill_ratios else 0.0,
        "rewrite_reclaim_bytes": rewritten_delete_bytes,
        "bytes_after": bytes_before,
    }

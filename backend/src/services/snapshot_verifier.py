"""算法 B｜快照 diff 与守恒校验 + 流读冲突窗口。

守恒口径（可手算）：
- 表级校验和 combine(files) = (Σ data.checksum) mod 2^32  XOR  (⊕ delete.checksum)
  合并后的文件 checksum 取被合并文件 checksum 之和（同余模 2^32），因此
  「合并前后 Σ 校验和」在数学上必须相等；delete 文件用缺位异或，rewrite 收敛后同样必须相等。
- 行数守恒：Σ rows_after(data) == Σ rows_before(data)。delete 文件不带数据行。
- added / removed 按 manifest 的 path 集合求差；rewritten = 同一分区分组内既有 removed 又有 added。

冲突窗口：
- 保护区间 [job_start - flow_lag, job_end] 与表的流读窗口 [stream_start, stream_end] 相交即 conflict=true；
- 建议窗口 = 流读窗口结束 + 冷却时间（默认 15 分钟）起的连续时段。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

MOD32 = 1 << 32
COOLDOWN_MINUTES = 15


def _kind(item: dict) -> str:
    return str(item.get("kind") or "data")


def _checksum(item: dict) -> int | None:
    value = item.get("checksum")
    if value is None:
        return None
    try:
        return int(value) % MOD32
    except (TypeError, ValueError):
        return None


def combine_checksum(files: list[dict]) -> int:
    """表级校验和：数据文件按行的校验和求和，delete 文件缺位异或。"""
    data_sum = 0
    delete_xor = 0
    for item in files:
        cks = _checksum(item)
        if cks is None:
            continue
        if _kind(item) == "delete":
            delete_xor ^= cks
        else:
            data_sum = (data_sum + cks) % MOD32
    return (data_sum ^ delete_xor) % MOD32


def _missing_checksum(files: list[dict]) -> bool:
    return any(_checksum(item) is None for item in files)


def manifest_summary(files: list[dict]) -> dict:
    data = [item for item in files if _kind(item) != "delete"]
    deletes = [item for item in files if _kind(item) == "delete"]
    return {
        "data_file_count": len(data),
        "delete_file_count": len(deletes),
        "total_rows": sum(int(item.get("rows") or 0) for item in data),
        "checksum": combine_checksum(files),
        "bytes": sum(int(item.get("bytes") or 0) for item in files),
        "file_count": len(files),
    }


def verify_manifests(before_files: list[dict], after_files: list[dict]) -> dict:
    before_by_path = {str(item.get("path")): item for item in before_files}
    after_by_path = {str(item.get("path")): item for item in after_files}

    added = [after_by_path[path] for path in sorted(after_by_path) if path not in before_by_path]
    removed = [before_by_path[path] for path in sorted(before_by_path) if path not in after_by_path]
    unchanged = [path for path in sorted(after_by_path) if path in before_by_path]

    partitions = sorted({str(item.get("partition_key") or "") for item in before_files + after_files})
    rewritten: list[dict] = []
    partition_rows: list[dict] = []
    for key in partitions:
        before_part = [item for item in before_files if str(item.get("partition_key") or "") == key]
        after_part = [item for item in after_files if str(item.get("partition_key") or "") == key]
        part_removed = [item for item in before_part if str(item.get("path")) not in after_by_path]
        part_added = [item for item in after_part if str(item.get("path")) not in before_by_path]
        rows_in = sum(int(item.get("rows") or 0) for item in before_part if _kind(item) != "delete")
        rows_out = sum(int(item.get("rows") or 0) for item in after_part if _kind(item) != "delete")
        if part_removed and part_added:
            rewritten.append(
                {
                    "partition_key": key,
                    "files_in": len(part_removed),
                    "files_out": len(part_added),
                    "rows_in": sum(int(item.get("rows") or 0) for item in part_removed if _kind(item) != "delete"),
                    "rows_out": sum(int(item.get("rows") or 0) for item in part_added if _kind(item) != "delete"),
                    "checksum_in": combine_checksum(part_removed),
                    "checksum_out": combine_checksum(part_added),
                }
            )
        if part_removed or part_added:
            partition_rows.append(
                {
                    "partition_key": key,
                    "rows_before": rows_in,
                    "rows_after": rows_out,
                    "rows_delta": rows_out - rows_in,
                    "files_before": len(before_part),
                    "files_after": len(after_part),
                }
            )

    before_summary = manifest_summary(before_files)
    after_summary = manifest_summary(after_files)
    rows_before = before_summary["total_rows"]
    rows_after = after_summary["total_rows"]
    checksum_before = before_summary["checksum"]
    checksum_after = after_summary["checksum"]

    reasons: list[str] = []
    missing = (_missing_checksum(before_files) or _missing_checksum(after_files))
    if not before_files or not after_files:
        verdict = "unverifiable"
        reasons.append("manifest_missing")
    elif missing:
        verdict = "unverifiable"
        reasons.append("checksum_missing")
    else:
        rows_ok = rows_before == rows_after
        checksum_ok = checksum_before == checksum_after
        if rows_ok and checksum_ok:
            verdict = "consistent"
            reasons.append("rows_and_checksum_preserved")
        else:
            verdict = "lossy"
            if not rows_ok:
                reasons.append("rows_mismatch")
            if not checksum_ok:
                reasons.append("checksum_mismatch")

    lossy_partitions = [row for row in partition_rows if row["rows_delta"] != 0]
    return {
        "verdict": verdict,
        "reasons": reasons,
        "before": before_summary,
        "after": after_summary,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_delta": rows_after - rows_before,
        "checksum_before": checksum_before,
        "checksum_after": checksum_after,
        "checksum_delta": (checksum_after - checksum_before) % MOD32,
        "rows_conserved": rows_before == rows_after,
        "checksum_conserved": checksum_before == checksum_after,
        "added": [_brief(item) for item in added],
        "removed": [_brief(item) for item in removed],
        "unchanged_count": len(unchanged),
        "rewritten": rewritten,
        "partitions": partition_rows,
        "lossy_partitions": lossy_partitions,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "rewritten": len(rewritten),
            "unchanged": len(unchanged),
        },
    }


def _brief(item: dict) -> dict:
    return {
        "path": item.get("path"),
        "partition_key": item.get("partition_key"),
        "kind": _kind(item),
        "bytes": int(item.get("bytes") or 0),
        "rows": int(item.get("rows") or 0),
        "checksum": item.get("checksum"),
    }


def _minutes(text: str) -> int:
    hour, _, minute = str(text).partition(":")
    return int(hour or 0) * 60 + int(minute or 0)


def _at(day: date, minutes: int) -> datetime:
    return datetime(day.year, day.month, day.day) + timedelta(minutes=minutes)


def check_window(
    *,
    job_start: datetime | None,
    job_end: datetime | None,
    flow_lag_seconds: int,
    stream_start: str = "00:00",
    stream_end: str = "06:30",
    cooldown_minutes: int = COOLDOWN_MINUTES,
) -> dict:
    if job_start is None or job_end is None:
        return {"conflict": False, "reason": "window_missing", "overlap_minutes": 0, "guard_start": None}

    lag = max(0, int(flow_lag_seconds))
    guard_start = job_start - timedelta(seconds=lag)
    duration_minutes = max(0, int((job_end - job_start).total_seconds() // 60))

    day = guard_start.date()
    start_min = _minutes(stream_start)
    end_min = _minutes(stream_end)
    stream_begin = _at(day, start_min)
    stream_finish = _at(day, end_min)
    if end_min <= start_min:
        stream_finish += timedelta(days=1)

    overlap_start = max(guard_start, stream_begin)
    overlap_end = min(job_end, stream_finish)
    overlap_minutes = int((overlap_end - overlap_start).total_seconds() // 60) if overlap_end > overlap_start else 0
    conflict = overlap_minutes > 0

    suggested_start = stream_finish + timedelta(minutes=cooldown_minutes)
    suggested_end = suggested_start + timedelta(minutes=duration_minutes)
    return {
        "conflict": conflict,
        "reason": "stream_window_overlap" if conflict else "outside_stream_window",
        "guard_start": guard_start.isoformat(timespec="minutes"),
        "job_start": job_start.isoformat(timespec="minutes"),
        "job_end": job_end.isoformat(timespec="minutes"),
        "flow_lag_seconds": lag,
        "stream_window": {"start": stream_start, "end": stream_end},
        "overlap_start": overlap_start.isoformat(timespec="minutes") if conflict else None,
        "overlap_end": overlap_end.isoformat(timespec="minutes") if conflict else None,
        "overlap_minutes": overlap_minutes,
        "duration_minutes": duration_minutes,
        "suggested_window": {
            "start": suggested_start.isoformat(timespec="minutes"),
            "end": suggested_end.isoformat(timespec="minutes"),
        },
        "suggestion_note": f"流读窗口 {stream_start}-{stream_end} 结束后冷却 {cooldown_minutes} 分钟再执行",
    }

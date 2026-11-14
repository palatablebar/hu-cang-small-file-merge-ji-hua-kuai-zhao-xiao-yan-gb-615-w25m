"""演示数据定义：6 张湖表 / 36 个分区 / 1167 个文件 / 3 组快照 / 4 个合并计划。

全部数值由 code 与序号确定性派生（同一份代码两次执行产出一致），便于幂等 seed 与手算复核。
"""
from __future__ import annotations

from zlib import crc32

DEMO_PASSWORD = "Demo@2026"
ORG = "陆港物流 · 数据平台组"

DEMO_USERS = [
    ("admin@compactlab.io", "林可", "admin"),
    ("analyst@compactlab.io", "周棠", "analyst"),
    ("viewer@compactlab.io", "陈默", "viewer"),
]

MIB = 1024 * 1024
TARGET_128 = 128 * MIB
SEED_DATE = "2026-11-13"
SEED_PLAN_PREFIX = "CP20261113"

TABLES = [
    {
        "code": "ods_flink_landing",
        "name": "Flink 落地区 ODS",
        "layer": "ods",
        "fmt": "iceberg",
        "location": "s3://lg-lake/warehouse/ods/flink_landing",
        "partition_spec": "days(dt), hours(hour)",
        "target_bytes": TARGET_128,
        "min_files": 5,
        "flow_lag_seconds": 900,
        "stream_window": ("00:00", "06:30"),
        "counts": [60, 58, 55, 52, 49, 46],
        "note": "Flink 每小时 commit 一次，单文件 2-28 MiB，小文件最集中",
    },
    {
        "code": "dwd_order_detail",
        "name": "订单明细 DWD",
        "layer": "dwd",
        "fmt": "iceberg",
        "location": "s3://lg-lake/warehouse/dwd/order_detail",
        "partition_spec": "days(dt), hours(hour)",
        "target_bytes": TARGET_128,
        "min_files": 5,
        "flow_lag_seconds": 900,
        "stream_window": ("00:00", "06:30"),
        "counts": [48, 36, 32, 28, 24, 21],
        "engineered_hour": "00",
        "note": "验收分区：dt=2026-11-13/hour=00 共 48 文件，FFD 装箱后必须正好 25 组",
    },
    {
        "code": "dwd_shipment_track",
        "name": "运单轨迹 DWD",
        "layer": "dwd",
        "fmt": "iceberg",
        "location": "s3://lg-lake/warehouse/dwd/shipment_track",
        "partition_spec": "days(dt), hours(hour)",
        "target_bytes": TARGET_128,
        "min_files": 5,
        "flow_lag_seconds": 600,
        "stream_window": ("00:00", "06:30"),
        "counts": [44, 41, 38, 35, 30, 26],
        "delete_hour": "03",
        "note": "含 position delete 文件的分区，必须先 rewrite 才能合并",
    },
    {
        "code": "dws_route_daily",
        "name": "线路日汇总 DWS",
        "layer": "dws",
        "fmt": "iceberg",
        "location": "s3://lg-lake/warehouse/dws/route_daily",
        "partition_spec": "days(dt), hours(hour)",
        "target_bytes": TARGET_128,
        "min_files": 5,
        "flow_lag_seconds": 1800,
        "stream_window": ("01:00", "05:00"),
        "counts": [30, 28, 26, 24, 22, 20],
        "note": "汇总层，流读窗口 01:00-05:00，凌晨合并最容易撞上",
    },
    {
        "code": "dim_port_calendar",
        "name": "港口日历 DIM",
        "layer": "dim",
        "fmt": "paimon",
        "location": "s3://lg-lake/warehouse/dim/port_calendar",
        "partition_spec": "days(dt), hours(hour)",
        "target_bytes": TARGET_128,
        "min_files": 5,
        "flow_lag_seconds": 300,
        "stream_window": ("00:00", "02:00"),
        "counts": [24, 22, 3, 20, 20, 20],
        "note": "hour=02 只有 3 个文件，低于最小文件数，计划里应跳过",
    },
    {
        "code": "ads_dispatch_board",
        "name": "调度看板 ADS",
        "layer": "ads",
        "fmt": "hudi",
        "location": "s3://lg-lake/warehouse/ads/dispatch_board",
        "partition_spec": "days(dt), hours(hour)",
        "target_bytes": TARGET_128,
        "min_files": 5,
        "flow_lag_seconds": 900,
        "stream_window": ("00:00", "06:30"),
        "counts": [40, 36, 32, 28, 24, 22],
        "oversized_hour": "01",
        "delete_hour": "05",
        "note": "hour=01 有两个 150MB+ 的大文件不参与合并；hour=05 含 delete 文件",
    },
]

HOURS = ["00", "01", "02", "03", "04", "05"]

# 快照用例：3 组（before/after），分别覆盖 consistent / lossy / unverifiable
SNAPSHOT_CASES = [
    {
        "table_code": "ods_flink_landing",
        "seq_no": 1,
        "mode": "consistent",
        "note": "合并前后行数与校验和完全一致",
    },
    {
        "table_code": "dwd_order_detail",
        "seq_no": 1,
        "mode": "lossy",
        "note": "合并后少 3 行，必须判 lossy 并阻断该表的计划执行",
    },
    {
        "table_code": "ads_dispatch_board",
        "seq_no": 1,
        "mode": "unverifiable",
        "note": "合并后快照缺 checksum，只能判 unverifiable",
    },
]

# 4 个合并计划：已执行 1 / 被阻断 1 / 待执行 2（其中 1 个撞流读窗口）
SEED_JOBS = [
    {
        "seed_key": "seed-plan-1",
        "plan_no": f"{SEED_PLAN_PREFIX}-0001",
        "table_code": "ods_flink_landing",
        "trigger": "schedule",
        "status": "executed",
        "window": ("2026-11-13T07:30", "2026-11-13T08:30"),
        "operator": "admin@compactlab.io",
        "review_status": "confirmed",
        "reviewer": "admin@compactlab.io",
        "review_note": "夜班已确认，合并收益 47% 文件数降幅，快照守恒",
        "snapshot_seq": 1,
    },
    {
        "seed_key": "seed-plan-2",
        "plan_no": f"{SEED_PLAN_PREFIX}-0002",
        "table_code": "dwd_order_detail",
        "trigger": "manual",
        "status": "blocked",
        "window": ("2026-11-13T09:00", "2026-11-13T10:00"),
        "operator": "admin@compactlab.io",
        "review_status": "pending",
        "reviewer": None,
        "review_note": None,
        "snapshot_seq": 1,
    },
    {
        "seed_key": "seed-plan-3",
        "plan_no": f"{SEED_PLAN_PREFIX}-0003",
        "table_code": "dws_route_daily",
        "trigger": "manual",
        "status": "planned",
        "window": ("2026-11-13T02:00", "2026-11-13T03:00"),
        "operator": "admin@compactlab.io",
        "review_status": "pending",
        "reviewer": None,
        "review_note": None,
        "snapshot_seq": 0,
    },
    {
        "seed_key": "seed-plan-4",
        "plan_no": f"{SEED_PLAN_PREFIX}-0004",
        "table_code": "ads_dispatch_board",
        "trigger": "backfill",
        "status": "planned",
        "window": ("2026-11-13T20:00", "2026-11-13T21:00"),
        "operator": "analyst@compactlab.io",
        "review_status": "dismissed",
        "reviewer": "analyst@compactlab.io",
        "review_note": "先做 rewrite 再排合并，本轮计划驳回",
        "snapshot_seq": 1,
    },
]

SEED_AUDITS = [
    ("seed-audit-1", "admin@compactlab.io", "admin", "table.create", "lake_table", {"code": "ods_flink_landing"}),
    ("seed-audit-2", "analyst@compactlab.io", "analyst", "file.scan", "lake_table", {"files": 1167, "partitions": 36}),
    ("seed-audit-3", "admin@compactlab.io", "admin", "plan.create", "compaction_job", {"plan_no": f"{SEED_PLAN_PREFIX}-0001"}),
]


def partition_key(hour: str) -> str:
    return f"dt={SEED_DATE}/hour={hour}"


def normal_file(table_code: str, location: str, key: str, index: int, seed_salt: int) -> dict:
    mib = 2 + ((index * 7 + seed_salt) % 27)
    size = mib * MIB + index * 4096
    rows = 880 + (index * 137) % 620
    path = f"{location}/{key}/part-{index:04d}.parquet"
    checksum = crc32(f"{path}|{size}|{rows}".encode()) % (1 << 32)
    return {
        "path": path,
        "partition_key": key,
        "kind": "data",
        "bytes": size,
        "rows": rows,
        "checksum": checksum,
        "file_no": index,
    }


def engineered_files(table_code: str, location: str, key: str) -> list[dict]:
    """验收分区：25 个 0.55×target 大文件 + 23 个 0.45×target 小文件。

    48 个文件、总字节 = 3,234,647,244（约 3.2 GB）；FFD（容量 128 MiB）严格装箱成 25 桶，
    与理论下界 ceil(total/target)=25 相等。io_saved_ratio = (48-25)/48 = 0.4792。
    """
    anchor = int(TARGET_128 * 0.55)
    filler = TARGET_128 - anchor
    files: list[dict] = []
    index = 0
    for i in range(25):
        path = f"{location}/{key}/anchor-{i:04d}.parquet"
        rows = 1200 + i * 11
        files.append(
            {
                "path": path,
                "partition_key": key,
                "kind": "data",
                "bytes": anchor,
                "rows": rows,
                "checksum": crc32(f"{path}|{anchor}|{rows}".encode()) % (1 << 32),
                "file_no": index,
            }
        )
        index += 1
    for i in range(23):
        path = f"{location}/{key}/filler-{i:04d}.parquet"
        rows = 640 + i * 7
        files.append(
            {
                "path": path,
                "partition_key": key,
                "kind": "data",
                "bytes": filler,
                "rows": rows,
                "checksum": crc32(f"{path}|{filler}|{rows}".encode()) % (1 << 32),
                "file_no": index,
            }
        )
        index += 1
    return files


def oversized_file(location: str, key: str, index: int, mib: int) -> dict:
    size = mib * MIB
    rows = 9800 + index * 400
    path = f"{location}/{key}/big-{index:04d}.parquet"
    return {
        "path": path,
        "partition_key": key,
        "kind": "data",
        "bytes": size,
        "rows": rows,
        "checksum": crc32(f"{path}|{size}|{rows}".encode()) % (1 << 32),
        "file_no": 900 + index,
    }


def delete_file(location: str, key: str, index: int) -> dict:
    size = (1 + index) * 256 * 1024
    rows = 0
    path = f"{location}/{key}/delete-{index:04d}.pos-del.parquet"
    return {
        "path": path,
        "partition_key": key,
        "kind": "delete",
        "bytes": size,
        "rows": rows,
        "checksum": crc32(f"{path}|{size}|del".encode()) % (1 << 32),
        "file_no": 950 + index,
    }


def files_for_partition(table: dict, hour: str, seed_salt: int) -> list[dict]:
    key = partition_key(hour)
    location = table["location"]
    index = HOURS.index(hour)
    count = table["counts"][index]
    if table.get("engineered_hour") == hour:
        files = engineered_files(table["code"], location, key)
    else:
        files = [normal_file(table["code"], location, key, i, seed_salt) for i in range(count)]
    if table.get("oversized_hour") == hour:
        files.extend([oversized_file(location, key, 0, 150), oversized_file(location, key, 1, 160)])
    if table.get("delete_hour") == hour:
        files.extend([delete_file(location, key, 0), delete_file(location, key, 1)])
    return files

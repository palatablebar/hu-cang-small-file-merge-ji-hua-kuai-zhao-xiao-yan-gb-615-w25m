"""共享枚举（后端唯一定义处）。前端副本见 frontend/site/js/config.js。

README「共享枚举出现位置」一节列出全部出现点，改动需两侧同步。
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Layer(StrEnum):
    """分区分层：ODS 落地 / DWD 明细 / DWS 汇总 / DIM 维表 / ADS 应用。"""

    ODS = "ods"
    DWD = "dwd"
    DWS = "dws"
    DIM = "dim"
    ADS = "ads"


LAYER_LABELS: dict[str, str] = {
    Layer.ODS.value: "ODS 落地层",
    Layer.DWD.value: "DWD 明细层",
    Layer.DWS.value: "DWS 汇总层",
    Layer.DIM.value: "DIM 维表层",
    Layer.ADS.value: "ADS 应用层",
}

LAYER_ORDER: list[str] = [
    Layer.ODS.value,
    Layer.DWD.value,
    Layer.DWS.value,
    Layer.DIM.value,
    Layer.ADS.value,
]


class TableFormat(StrEnum):
    ICEBERG = "iceberg"
    HUDI = "hudi"
    PAIMON = "paimon"


TABLE_FORMAT_LABELS: dict[str, str] = {
    TableFormat.ICEBERG.value: "Iceberg v2",
    TableFormat.HUDI.value: "Hudi MOR",
    TableFormat.PAIMON.value: "Paimon",
}


class FileKind(StrEnum):
    DATA = "data"
    DELETE = "delete"


FILE_KIND_LABELS: dict[str, str] = {
    FileKind.DATA.value: "数据文件",
    FileKind.DELETE.value: "删除文件",
}


class JobStatus(StrEnum):
    """合并计划状态：planned 待执行 / executed 已执行 / blocked 被校验阻断 / failed 失败。"""

    PLANNED = "planned"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    FAILED = "failed"


JOB_STATUS_LABELS: dict[str, str] = {
    JobStatus.PLANNED.value: "待执行",
    JobStatus.EXECUTED.value: "已执行",
    JobStatus.BLOCKED.value: "校验阻断",
    JobStatus.FAILED.value: "执行失败",
}

JOB_STATUS_ORDER: list[str] = [
    JobStatus.PLANNED.value,
    JobStatus.EXECUTED.value,
    JobStatus.BLOCKED.value,
    JobStatus.FAILED.value,
]


class VerifyVerdict(StrEnum):
    """快照守恒判定。"""

    CONSISTENT = "consistent"
    LOSSY = "lossy"
    UNVERIFIABLE = "unverifiable"


VERDICT_LABELS: dict[str, str] = {
    VerifyVerdict.CONSISTENT.value: "守恒一致",
    VerifyVerdict.LOSSY.value: "行数/校验和不守恒",
    VerifyVerdict.UNVERIFIABLE.value: "不可判定",
}

VERDICT_ORDER: list[str] = [
    VerifyVerdict.CONSISTENT.value,
    VerifyVerdict.LOSSY.value,
    VerifyVerdict.UNVERIFIABLE.value,
]


class SnapshotLabel(StrEnum):
    BEFORE = "before"
    AFTER = "after"


SNAPSHOT_LABEL_LABELS: dict[str, str] = {
    SnapshotLabel.BEFORE.value: "合并前",
    SnapshotLabel.AFTER.value: "合并后",
}


class TriggerKind(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    BACKFILL = "backfill"


TRIGGER_LABELS: dict[str, str] = {
    TriggerKind.MANUAL.value: "手动编排",
    TriggerKind.SCHEDULE.value: "定时策略",
    TriggerKind.BACKFILL.value: "补数重跑",
}


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_LABELS: dict[str, str] = {
    Severity.HIGH.value: "高",
    Severity.MEDIUM.value: "中",
    Severity.LOW.value: "低",
}

SEVERITY_ORDER: list[str] = [Severity.HIGH.value, Severity.MEDIUM.value, Severity.LOW.value]


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


REVIEW_STATUS_LABELS: dict[str, str] = {
    ReviewStatus.PENDING.value: "待复核",
    ReviewStatus.CONFIRMED.value: "已确认",
    ReviewStatus.DISMISSED.value: "已驳回",
}

REVIEW_STATUS_ORDER: list[str] = [
    ReviewStatus.PENDING.value,
    ReviewStatus.CONFIRMED.value,
    ReviewStatus.DISMISSED.value,
]


# 小文件口径：小于 32 MiB 视为小文件（元数据膨胀的主要来源）
SMALL_FILE_BYTES = 32 * 1024 * 1024
# 默认目标文件大小 128 MiB
DEFAULT_TARGET_BYTES = 128 * 1024 * 1024
# 每分区最小文件数：低于该值不合并
DEFAULT_MIN_FILES = 5
# 流读保护:合并窗口取流读结束后 15 分钟冷却
WRITE_COOLDOWN_MINUTES = 15

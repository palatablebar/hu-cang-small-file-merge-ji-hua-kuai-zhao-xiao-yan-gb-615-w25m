"""角色 -> 权限点映射。README 与前端 site/js/config.js 同步。

角色键固定为 admin / analyst / viewer，各项目的展示名与职责不同。
"""
from __future__ import annotations

from src.constants.enums import Role

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "平台管理员",
    Role.ANALYST.value: "数据专员",
    Role.VIEWER.value: "值班只读",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "登记湖表与分区、生成与执行合并计划、导出报表、查看审计",
    Role.ANALYST.value: "扫描 manifest、预览合并计划、做快照守恒校验、复核计划结论",
    Role.VIEWER.value: "只读查看小文件与合并收益比例，不能建计划、不能执行、不能导出",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "overview:read",
        "table:read", "table:write",
        "partition:read",
        "file:read", "file:scan",
        "plan:read", "plan:create", "plan:execute", "plan:review",
        "snapshot:read", "snapshot:verify",
        "export:read", "audit:read",
    },
    Role.ANALYST.value: {
        "overview:read",
        "table:read",
        "partition:read",
        "file:read", "file:scan",
        "plan:read", "plan:review",
        "snapshot:read", "snapshot:verify",
    },
    Role.VIEWER.value: {
        "overview:read",
        "table:read",
        "partition:read",
        "file:read",
        "plan:read",
        "snapshot:read",
    },
}

TABLE_WRITE_ROLES = (Role.ADMIN.value,)
PLAN_CREATE_ROLES = (Role.ADMIN.value,)
PLAN_EXECUTE_ROLES = (Role.ADMIN.value,)
PLAN_REVIEW_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
SCAN_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
SNAPSHOT_VERIFY_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
EXPORT_ROLES = (Role.ADMIN.value,)
AUDIT_ROLES = (Role.ADMIN.value,)
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.VIEWER.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())

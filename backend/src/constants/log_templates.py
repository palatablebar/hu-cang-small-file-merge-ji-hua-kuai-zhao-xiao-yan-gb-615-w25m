"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "table.create": "登记湖表",
    "table.update": "修改湖表",
    "file.scan": "扫描文件清单",
    "plan.create": "生成合并计划",
    "plan.execute": "执行合并计划",
    "plan.block": "快照校验阻断执行",
    "plan.review": "复核计划",
    "snapshot.verify": "快照守恒校验",
    "export.plans": "导出合并计划",
    "export.snapshots": "导出快照校验",
    "http.mutation": "写请求",
}

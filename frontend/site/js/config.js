/**
 * 项目品牌、导航、角色权限与枚举文案（前端唯一定义处）。
 * 后端对应：backend/src/constants/{roles,enums}.py；README「共享枚举出现位置」一节列出全部出现点。
 */
export const BRAND = {
  short: 'compactlab',
  title: '湖仓小文件合并计划与快照校验',
  org: '陆港物流 · 数据平台组',
  edition: 'COMPACT LAB · 2026',
  subtitle: 'manifest 扫描 → 合并计划 → 冲突窗口 → 快照守恒，一条链路说清「合并后数据没丢」',
  loginLead:
    'Flink 每小时落盘，一天新增 1200+ 小文件；合并脚本谁都能跑，但没人能证明行数和校验和没变。这里把计划和证据放在一起。',
  loginSteps: [
    ['01', 'manifest 扫描', '分区 / 文件 / delete 明细一次入库'],
    ['02', '合并计划', 'FFD 装箱 + 目标 128MB + delete 分区先 rewrite'],
    ['03', '快照守恒', '行数与校验和比对，lossy 直接阻断执行'],
  ],
};

export const NAV = [
  { to: '#/overview', no: '01', label: '总览', permission: 'overview:read' },
  { to: '#/tables', no: '02', label: '表与分区', permission: 'table:read' },
  { to: '#/files', no: '03', label: '文件清单', permission: 'file:read' },
  { to: '#/plans', no: '04', label: '合并计划', permission: 'plan:read' },
  { to: '#/snapshots', no: '05', label: '快照校验与导出', permission: 'snapshot:read' },
];

export const ROLE_LABELS = {
  admin: '平台管理员',
  analyst: '数据专员',
  viewer: '值班只读',
};

export const PERMISSIONS = {
  admin: [
    'overview:read',
    'table:read',
    'table:write',
    'partition:read',
    'file:read',
    'file:scan',
    'plan:read',
    'plan:create',
    'plan:execute',
    'plan:review',
    'snapshot:read',
    'snapshot:verify',
    'export:read',
    'audit:read',
  ],
  analyst: [
    'overview:read',
    'table:read',
    'partition:read',
    'file:read',
    'file:scan',
    'plan:read',
    'plan:review',
    'snapshot:read',
    'snapshot:verify',
  ],
  viewer: ['overview:read', 'table:read', 'partition:read', 'file:read', 'plan:read', 'snapshot:read'],
};

export const ENUMS = {
  layer: {
    ods: 'ODS 落地层',
    dwd: 'DWD 明细层',
    dws: 'DWS 汇总层',
    dim: 'DIM 维表层',
    ads: 'ADS 应用层',
  },
  fmt: {
    iceberg: 'Iceberg v2',
    hudi: 'Hudi MOR',
    paimon: 'Paimon',
  },
  fileKind: {
    data: '数据文件',
    delete: '删除文件',
  },
  jobStatus: {
    planned: '待执行',
    executed: '已执行',
    blocked: '校验阻断',
    failed: '执行失败',
  },
  verdict: {
    consistent: '守恒一致',
    lossy: '行数/校验和不守恒',
    unverifiable: '不可判定',
  },
  review: {
    pending: '待复核',
    confirmed: '已确认',
    dismissed: '已驳回',
  },
  trigger: {
    manual: '手动编排',
    schedule: '定时策略',
    backfill: '补数重跑',
  },
};

export function can(role, permission) {
  return (PERMISSIONS[role] || []).includes(permission);
}

export function statusTone(status) {
  return { planned: 'warn', executed: 'ok', blocked: 'danger', failed: 'danger' }[status] || 'info';
}

export function verdictTone(verdict) {
  return { consistent: 'ok', lossy: 'danger', unverifiable: 'warn' }[verdict] || 'info';
}

export function reviewTone(status) {
  return { pending: 'warn', confirmed: 'ok', dismissed: 'danger' }[status] || 'info';
}

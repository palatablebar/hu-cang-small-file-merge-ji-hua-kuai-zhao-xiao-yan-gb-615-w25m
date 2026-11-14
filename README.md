# 湖仓小文件合并计划与快照校验（`compactlab`）

> 数据工程 · 中型多模块项目。原生 HTML/CSS/JS 前端 + Python FastAPI 后端 + Celery worker + PostgreSQL 16 + Redis，5 个容器一键起。

## 1. 场景

- **模拟客户**：陆港物流 · 数据平台组（9 人），湖仓按小时落盘（Iceberg v2 风格 manifest），日增 1200+ 小文件，查询引擎元数据膨胀。
- **现有工作流**：DBA 每周手工跑一次合并脚本（翻 manifest 目录 → 按经验挑分区 → 夜间执行），跑完没人敢确认数据没丢，值班只在群里问一句「今天谁合并了」。
- **三个痛点**：
  1. 小文件多、查询慢：单个分区几十个 2–28 MiB 文件，目标 128 MiB 却没人装箱；
  2. 合并与流式读冲突：凌晨乱跑把 Flink 读任务打挂，窗口靠人记；
  3. 合并后无法证明行数/校验和没变：没有 before/after 快照 diff，也没有守恒结论。
- **上下游**：上游 Flink 落盘（写 manifest）→ **本系统**（manifest 扫描 → 合并计划 → 冲突窗口校验 → 执行模拟 → 快照 diff 守恒校验）→ 查询引擎 / 值班群 / 周报。
- **一天的工作剧本**：
  1. 08:10 数据专员点「重扫 manifest」，36 个分区的文件数/体积/delete 标记刷新；
  2. 08:20 值班只读打开总览，看到小文件占比 95.7%、最近一次合并省了 87.2% 文件数（只显示比例）；
  3. 09:00 管理员对 `dwd_order_detail` 生成合并计划，算法 A 把 189 个文件装成 44 组，hour=00 那个 48 文件 / 3.2 GB 分区正好 25 组；
  4. 09:05 计划被「快照校验」门禁拦住：该表上一轮 after 快照少了 3 行（lossy），执行返回 409；
  5. 10:00 管理员改选 `dws_route_daily`，但窗口 02:00–03:00 撞上流读 01:00–05:00，冲突 75 分钟，系统给出建议窗口 06:45–07:45；
  6. 10:30 重排窗口到 20:00–21:00 后执行成功：落 before/after 快照，行数与校验和守恒（consistent）；
  7. 10:40 数据专员复核计划结论「已确认」，备注写清窗口依据；
  8. 10:45 管理员导出合并计划 CSV 与快照校验 CSV，审计里留下 export 记录；
  9. 20:00 worker 心跳与每日 manifest 重扫任务在岗，总览右上角显示「后台任务 · 在岗」。

## 2. 角色与权限

| 角色 | 账号 | 权限 | 典型动作 |
|---|---|---|---|
| 平台管理员 `admin` | `admin@compactlab.io` | 读写湖表 + 生成/执行计划 + 复核 + 导出 + 审计 | 登记湖表、生成合并计划、执行、导出 CSV、看审计 |
| 数据专员 `analyst` | `analyst@compactlab.io` | 扫描 + 预览 + 快照校验 + 复核 | 重扫 manifest、复算快照守恒、复核计划结论 |
| 值班只读 `viewer` | `viewer@compactlab.io` | 只读列表与明细，收益只显示比例 | 看小文件规模与合并收益比例，不能建计划/执行/导出 |

密码统一 `Demo@2026`。低权角色调用高权接口返回**真实 HTTP 403**（不是前端隐藏）：

| 接口 | admin | analyst | viewer |
|---|---|---|---|
| `POST /api/compaction-jobs`（建计划） | 201 | 403 | 403 |
| `POST /api/compaction-jobs/{id}/execute`（执行） | 200 / 409 | 403 | 403 |
| `PATCH /api/compaction-jobs/{id}/review`（复核） | 200 | 200 | 403 |
| `POST /api/files/scan`（扫描） | 200 | 200 | 403 |
| `POST /api/snapshots/verify`（守恒校验） | 200 | 200 | 403 |
| `GET /api/exports/*.csv`（导出） | 200 | 403 | 403 |
| `GET /api/audit`（审计） | 200 | 403 | 403 |

## 3. 业务模块表（6 个）

| # | 模块 | 对应页面 | 后端 services / controller | 主要 API |
|---|---|---|---|---|
| ① | 表与分区登记 | `#/tables`（表列表 + 分区抽屉） | `table_service` / `partition_service` + `table_controller` | `GET/POST /api/tables`、`PATCH /api/tables/{id}`、`GET /api/partitions` |
| ② | 文件清单扫描 | `#/files`（manifest 明细 + 扫描按钮） | `data_file_service` + `file_controller` | `GET /api/files`、`GET /api/files/stats`、`POST /api/files/scan` |
| ③ | 合并计划（算法 A） | `#/plans`（生成抽屉 + 分组预览） | `compaction_planner` + `job_service` + `job_controller` | `POST /api/compaction-jobs`、`GET /api/compaction-jobs/{id}` |
| ④ | 冲突窗口校验 | `#/plans`（冲突横幅 + 重排窗口抽屉） | `snapshot_verifier`（窗口部分）+ `job_service` | `GET /api/compaction-jobs/{id}/window`、`PATCH /api/compaction-jobs/{id}/window` |
| ⑤ | 快照 diff 与守恒校验（算法 B） | `#/snapshots`（校验抽屉） | `snapshot_verifier.verify_manifests` + `snapshot_service` + `snapshot_controller` | `GET /api/snapshots`、`GET /api/snapshots/{id}`、`POST /api/snapshots/verify` |
| ⑥ | 报表导出 | `#/snapshots` 的「导出」标签 | `export_service` + `export_controller` | `GET /api/exports/plans.csv`、`GET /api/exports/snapshots.csv` |

横切能力（不计入业务模块）：JWT 三角色鉴权（`middlewares/auth.py`、`rbac.py`）、审计（`middlewares/audit_logger.py` + `audit_service` + `#/snapshots` 审计标签）、限流（`middlewares/rate_limit.py`）、worker 心跳（`tasks.py`）。

## 4. 快速启动

```bash
cp .env.example .env          # 仓库里已带一份可直接用的 .env
docker compose up -d --build  # 5/5 healthy ≈ 20-40s
open http://localhost:18204
```

首次启动 backend 自动建表并执行一次 seed（`SEED_DEMO=true`）。seed 幂等，可重复执行：

```bash
docker compose exec -T backend python -m scripts.seed_demo
# SEED_SUMMARY brand=compactlab users=3 sources=6 runs=4 findings=1170 pending=2
```

`SEED_SUMMARY` 的键名照约定固定，映射口径：`sources` = 湖表数、`runs` = 合并计划数、`findings` = manifest 文件数、`pending` = 待复核计划数。

## 5. 本地开发

```bash
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
# 前端是静态站点，任意静态服务器即可（接口默认 /api -> 8000，nginx 反代会剥前缀）
cd frontend/site && python3 -m http.server 5173
```

## 6. 访问地址

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:18204 |
| 后端 API 文档 | http://localhost:19204/docs |
| 健康检查 | http://localhost:19204/api/health |
| 数据库映射 | localhost:17704 |

## 7. 技术栈

| 层 | 选型 |
|---|---|
| 前端 | 原生 HTML5 + CSS（oklch 令牌）+ ES Modules；无框架、无打包器 |
| 后端 | Python 3.11、FastAPI 0.115、SQLAlchemy 2.0、PyJWT、passlib(bcrypt) |
| 异步 | Celery 5.4 + Redis（worker 心跳 10s、每日 manifest 重扫） |
| 数据库 | PostgreSQL 16 |
| 部署 | Docker Compose，恰好 5 服务（frontend/backend/worker/db/redis），全部带 healthcheck |

## 8. 目录

```text
backend/
  src/config/       settings / database / celery_app / app 装配
  src/constants/    enums（共享枚举）、roles（权限点）、limits、log_templates
  src/models/       lake_table / partition / data_file / compaction_job / snapshot (+ user, audit)
  src/schemas/      table / compaction / snapshot / auth / common
  src/services/     compaction_planner(A) / snapshot_verifier(B) / job / snapshot / table /
                    partition / data_file / overview / export / audit / auth
  src/controllers/  table / file / job / snapshot / export / auth
  src/routes/       tables / partitions / files / jobs / snapshots / exports / overview / audit / auth / health
  scripts/          seed_demo.py、demo_config.py、worker_healthcheck.sh
  tests/            35 个用例（两算法 + 权限 + 参数校验 + seed 幂等 + 安全）
frontend/site/
  index.html  css/{tokens,app}.css
  js/{config,api,store,ui,app}.js  js/pages/{login,overview,tables,files,plans,snapshots}.js
```

## 9. 环境变量

见 `.env.example`：`COMPOSE_PROJECT_NAME`、`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT`、`DB_*`、`JWT_SECRET`、`REDIS_URL`、`SEED_DEMO`、`RATE_LIMIT_*`、`APP_TIMEZONE_OFFSET_MINUTES`。

## 10. 核心算法与口径

两个算法都是**后端 Python 真算**（`src/services/compaction_planner.py`、`src/services/snapshot_verifier.py`），纯函数、无外部依赖，前端只渲染接口返回，不做任何二次计算。

### 算法 A｜合并计划（First-Fit-Decreasing 装箱）

- 输入：分区内 active manifest（`path / kind / bytes / rows / checksum`），参数 `target_bytes`（默认 128 MiB）、`min_files`（默认 5）。
- 规则：
  1. 单文件 `bytes > target_bytes` 不参与合并，原样保留；
  2. 分区文件数 `< min_files` 跳过（`below_min_files`）；
  3. 含 `delete` 文件的分区本轮不装箱，标记 `needs_rewrite`（必须先 rewrite 收敛删除）；
  4. 其余分区把 data 文件按 `(bytes 降序, path 升序)` 排序后 FFD 装箱，桶容量 = `target_bytes`。
- 输出：`merge_groups[{partition_key, group_no, files, bytes, rows, checksum, fill_ratio, paths}]`、`expected_files_after`、`files_reduced`、`io_saved_ratio = files_reduced / files_before`、`bins_lower_bound = Σ ceil(total/target)`、`avg_fill_ratio`、`rewrite_partitions`、`skipped_partitions`。
- 可手算验收：`dwd_order_detail` 的 `dt=2026-11-13/hour=00` 分区：48 个文件（25 个 73,819,750 B + 23 个 60,397,978 B），总计 3,234,647,244 B ≈ 3.2 GB；FFD 容量 128 MiB → **25 组**，`expected_files_after=25`，`bins_lower_bound=25`，`io_saved_ratio=(48-25)/48=0.4792`。
- 失败态：`target_bytes<=0` / `min_files<1` 抛 `ValueError`；请求参数越界返回 422。

### 算法 B｜快照 diff 与守恒校验 + 冲突窗口

- manifest diff：按 `path` 集合求 `added / removed / unchanged`；同一分区同时有 removed 与 added → 记为 `rewritten`（含 `files_in/out`、`rows_in/out`、`checksum_in/out`）。
- 守恒口径：
  - 行数：`Σ rows_after(data) == Σ rows_before(data)`；
  - 校验和：`combine(files) = (Σ data.checksum mod 2^32) XOR (⊕ delete.checksum)`，合并文件的 checksum 取被合并文件之和（模 2^32），因此合并前后表级校验和必须相等。
- 判定：两者都成立 → `consistent`；任一不成立 → `lossy`（`reasons` 含 `rows_mismatch` / `checksum_mismatch`，并给出 `lossy_partitions` 定位分区）；manifest 为空或缺 checksum → `unverifiable`。
- 冲突窗口：保护区间 `[job_start - flow_lag, job_end]` 与表的流读窗口 `[stream_start, stream_end]` 求交，`overlap_minutes>0` → `conflict=true`；建议窗口 = 流读结束 + 15 分钟冷却起，长度等于原窗口时长。
- 门禁：执行合并前先查该表最近一次 `after` 快照结论，`lossy` → HTTP 409 `snapshot_lossy`；窗口冲突 → HTTP 409 `stream_conflict`。
- 示例（seed）：`dwd_order_detail` 的 after 快照 `rows 218341 → 218338`（-3）、checksum 未变 → `lossy / rows_mismatch`，该表计划 `CP20261113-0002` 被阻断；`ods_flink_landing` 382,085 行前后一致 → `consistent`。

## 11. 共享枚举出现位置

| 枚举 | 后端 | 前端 |
|---|---|---|
| 角色 `admin/analyst/viewer` | `backend/src/constants/{enums,roles}.py` | `frontend/site/js/config.js`（`PERMISSIONS`） |
| 分层 `ods/dwd/dws/dim/ads` | `backend/src/constants/enums.py`（`Layer`） | `frontend/site/js/config.js`（`ENUMS.layer`） |
| 表格式 `iceberg/hudi/paimon` | `backend/src/constants/enums.py`（`TableFormat`） | `ENUMS.fmt` |
| 文件类型 `data/delete` | `backend/src/constants/enums.py`（`FileKind`） | `ENUMS.fileKind` |
| 计划状态 `planned/executed/blocked/failed` | `backend/src/constants/enums.py`（`JobStatus`） | `ENUMS.jobStatus` |
| 守恒结论 `consistent/lossy/unverifiable` | `backend/src/constants/enums.py`（`VerifyVerdict`） | `ENUMS.verdict` |
| 复核状态 `pending/confirmed/dismissed` | `backend/src/constants/enums.py`（`ReviewStatus`） | `ENUMS.review` |
| 触发方式 `manual/schedule/backfill` | `backend/src/constants/enums.py`（`TriggerKind`） | `ENUMS.trigger` |

## 12. Docker 说明

- 5 个服务：`frontend`(Nginx 静态站) / `backend`(uvicorn) / `worker`(Celery beat+worker) / `db`(PostgreSQL 16) / `redis`，全部带 healthcheck。
- 命名卷：`db_data`、`redis_data`；`service_healthy` 依赖（db/redis → backend → worker/frontend）。
- Nginx：`location /api/ { proxy_pass http://backend:8000/; }` 剥前缀 + SPA 回落。
- 收尾：`docker compose down -v --remove-orphans`。

## 13. 视觉方向

`batch-plan.md` 未给 gb-615 指定单一视觉方向，按 BRIEF §3「每项一个方向」自行确定：**冷轧钢 + 铜标**——冷灰蓝工程纸（`--paper` oklch 0.958/0.006/240）+ 深钢色工作区（`--steel` oklch 0.245/0.028/252）+ 铜色标尺强调（`--accent` oklch 0.556/0.128/48）。
字体：`Space Grotesk`（标题与数字）+ `IBM Plex Sans SC`（正文）+ `IBM Plex Mono`（manifest 字段与编号）。
登录页是「值班链路 + 表单」双栏：左侧深钢色链路台账（扫描 → 计划 → 守恒），右侧纸面表单；总览头条是深钢色体检台 + 铜色收益比例。三档响应式：≥1280 / ≥768 / <768。

## License

内部演示项目，仅用于评测与教学。

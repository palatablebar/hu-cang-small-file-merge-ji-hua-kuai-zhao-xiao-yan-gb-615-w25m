"""路由聚合：统一 /api 前缀（Nginx 反代时剥掉 /api）。"""
from fastapi import APIRouter

from src.routes.audit import router as audit_router
from src.routes.auth import router as auth_router
from src.routes.exports import router as exports_router
from src.routes.files import router as files_router
from src.routes.health import router as health_router
from src.routes.jobs import router as jobs_router
from src.routes.overview import router as overview_router
from src.routes.partitions import router as partitions_router
from src.routes.snapshots import router as snapshots_router
from src.routes.tables import router as tables_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(tables_router)
api_router.include_router(partitions_router)
api_router.include_router(files_router)
api_router.include_router(jobs_router)
api_router.include_router(snapshots_router)
api_router.include_router(exports_router)
api_router.include_router(audit_router)

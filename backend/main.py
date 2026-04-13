"""
backend/main.py
FastAPI 应用入口：路由注册、CORS、lifespan、前端静态文件挂载。

启动命令：
  uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import scheduler as sch
from .process_manager import reload_registry
from .routers import downloaders, logs, schedule, config as config_router, records as records_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动建表 → 加载来源注册表 → 启动定时任务
    from downloaders.db import init_db
    init_db()
    reload_registry()
    sch.start()
    yield
    sch.shutdown()


app = FastAPI(title="标准下载管理平台", version="2.0", lifespan=lifespan)

# 支持通过环境变量 CORS_ORIGINS 覆盖（逗号分隔，或 * 表示全部允许）
# 容器部署时设置 CORS_ORIGINS=*，本地开发默认允许 Vite 开发服务器
_raw = os.environ.get("CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _raw.split(",") if o.strip()] if _raw else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(downloaders.router)
app.include_router(logs.router)
app.include_router(schedule.router)
app.include_router(config_router.router)
app.include_router(records_router.router)

# 生产环境挂载前端构建产物
_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")

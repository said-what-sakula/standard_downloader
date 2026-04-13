"""
backend/routers/config.py
配置管理 API：读取/保存 config.json 和来源列表（MySQL）。
"""

from fastapi import APIRouter, HTTPException, Body
from .. import config as cfg
from ..process_manager import reload_registry

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config():
    """读取服务器配置（config.json）"""
    return cfg.load()


@router.put("")
def update_config(body: dict = Body(...)):
    """保存服务器配置"""
    if "server" not in body:
        raise HTTPException(status_code=422, detail="缺少 server 字段")
    cfg.save(body)
    return {"ok": True}


@router.get("/sources")
def get_sources():
    """读取来源列表（MySQL）"""
    return cfg.load_sources()


@router.put("/sources")
def update_sources(body: list = Body(...)):
    """保存来源列表并刷新进程注册表"""
    cfg.save_sources(body)
    reload_registry()
    return {"ok": True}

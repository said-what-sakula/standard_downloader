"""
backend/routers/downloaders.py
下载器控制 API：列表、启动、停止、状态。
"""

from fastapi import APIRouter, HTTPException
from ..process_manager import get_process, all_statuses, reload_registry

router = APIRouter(prefix="/api/downloaders", tags=["downloaders"])


@router.get("")
def list_downloaders():
    """列出所有来源及状态"""
    reload_registry()
    return all_statuses()


@router.post("/{source_id}/start")
def start_downloader(source_id: str):
    reload_registry()
    try:
        proc = get_process(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"来源不存在: {source_id}")
    if proc.is_running:
        raise HTTPException(status_code=409, detail="已在运行中")
    ok = proc.start()
    if not ok:
        raise HTTPException(status_code=500, detail="启动失败")
    return {"ok": True, "status": proc.status()}


@router.post("/{source_id}/stop")
def stop_downloader(source_id: str):
    try:
        proc = get_process(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"来源不存在: {source_id}")
    if not proc.is_running:
        raise HTTPException(status_code=409, detail="未在运行")
    proc.stop()
    return {"ok": True}


@router.get("/{source_id}/status")
def downloader_status(source_id: str):
    try:
        proc = get_process(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"来源不存在: {source_id}")
    return proc.status()

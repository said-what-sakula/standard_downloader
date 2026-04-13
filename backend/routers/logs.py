"""
backend/routers/logs.py
日志管理 API：SSE 实时流、历史日志列表、日志文件读取与清空。
"""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import config as cfg
from ..process_manager import get_process

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/{source_id}/stream")
async def sse_stream(source_id: str):
    """Server-Sent Events：实时推送下载器 stdout"""
    try:
        proc = get_process(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"来源不存在: {source_id}")

    q = proc.subscribe_sse()

    async def generator():
        try:
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: \n\n"
                    continue

                if line == "__EOF__":
                    yield "event: close\ndata: 进程已结束\n\n"
                    break
                escaped = line.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"
        finally:
            proc.unsubscribe_sse(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{source_id}/history")
def list_history_logs(source_id: str):
    """列出该来源的所有日志文件（按修改时间倒序）"""
    log_dir = cfg.log_dir()
    files = []
    for p in log_dir.glob(f"{source_id}_*.log"):
        try:
            stat = p.stat()
            files.append({
                "filename": p.name,
                "size":     stat.st_size,
                "mtime":    stat.st_mtime,
            })
        except Exception:
            pass
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


@router.get("/{source_id}/file/{filename}")
def get_log_file(source_id: str, filename: str, tail: int = 2000, full: bool = False):
    """读取日志文件内容（纯文本）。tail=N 只返回最后 N 行，full=true 返回全量。"""
    # 安全校验：文件名只能以 source_id_ 开头
    if not filename.startswith(source_id + "_") or not filename.endswith(".log"):
        raise HTTPException(status_code=400, detail="非法文件名")
    log_path = cfg.log_dir() / filename
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    content = log_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    total_lines = len(lines)
    truncated = False
    if not full and total_lines > tail:
        lines = lines[-tail:]
        truncated = True
    return {
        "filename": filename,
        "content": "\n".join(lines),
        "total_lines": total_lines,
        "truncated": truncated,
        "shown_lines": len(lines),
    }


@router.delete("/{source_id}/clear/{filename}")
def clear_log_file(source_id: str, filename: str):
    """清空日志文件（下载器未运行时才允许）"""
    try:
        proc = get_process(source_id)
        if proc.is_running:
            raise HTTPException(status_code=409, detail="下载器运行中，不能清空日志")
    except KeyError:
        pass

    if not filename.startswith(source_id + "_") or not filename.endswith(".log"):
        raise HTTPException(status_code=400, detail="非法文件名")
    log_path = cfg.log_dir() / filename
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    log_path.write_text("", encoding="utf-8")
    return {"ok": True}

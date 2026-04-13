"""
backend/routers/records.py
标准库检索 API：分页搜索下载记录 + 获取详情（含元数据）+ 在线预览代理。
"""

import os
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse

router = APIRouter(prefix="/api/records", tags=["records"])

_CONTENT_TYPES = {
    ".pdf":  "application/pdf",
    ".doc":  "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls":  "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("")
def list_records(
    keyword:     str = Query(None, description="标准号或标准名称关键词"),
    source_type: str = Query(None, description="guobiao / hangbiao"),
    status:      str = Query(None, description="SUCCESS / NO_FULL_TEXT / ABOLISHED / ADOPTED / FAILED"),
    page:        int = Query(1,  ge=1),
    page_size:   int = Query(20, ge=1, le=100),
):
    from downloaders.db import search_records
    return search_records(
        keyword=keyword,
        source_type=source_type,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/{record_id}/preview")
async def preview_record(record_id: int):
    """
    文件预览 / 下载接口。优先使用 OSS URL（代理流），OSS 不可用时回退到本地文件。
    PDF 强制 inline 使浏览器直接渲染；其他格式以 attachment 触发下载。
    """
    from downloaders.db import get_record_detail
    result = get_record_detail(record_id)
    if result is None:
        raise HTTPException(status_code=404, detail="记录不存在")

    oss_url    = result.get("oss_url")
    local_path = result.get("local_path")

    if not oss_url and not local_path:
        raise HTTPException(status_code=404, detail="该记录暂无文件")

    # ── 优先 OSS 流式代理 ──────────────────────────────────────────────────────
    if oss_url:
        filename = (result.get("oss_path") or oss_url).rstrip("/").split("/")[-1] or "file"
        ext = os.path.splitext(filename)[1].lower()
        content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
        encoded_name = quote(filename, safe="")
        cd_header = f"inline; filename*=UTF-8''{encoded_name}" if ext == ".pdf" \
                    else f"attachment; filename*=UTF-8''{encoded_name}"

        async def _stream():
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                async with client.stream("GET", oss_url) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        yield chunk

        return StreamingResponse(
            _stream(),
            media_type=content_type,
            headers={"Content-Disposition": cd_header},
        )

    # ── 回退：直接返回本地文件 ─────────────────────────────────────────────────
    if not os.path.isfile(local_path):
        raise HTTPException(status_code=404, detail="本地文件不存在，可能已被移动或删除")

    filename = os.path.basename(local_path)
    ext = os.path.splitext(filename)[1].lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    encoded_name = quote(filename, safe="")
    cd_header = f"inline; filename*=UTF-8''{encoded_name}" if ext == ".pdf" \
                else f"attachment; filename*=UTF-8''{encoded_name}"

    return FileResponse(
        local_path,
        media_type=content_type,
        headers={"Content-Disposition": cd_header},
    )


@router.get("/{record_id}")
def get_record(record_id: int):
    from downloaders.db import get_record_detail
    result = get_record_detail(record_id)
    if result is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return result

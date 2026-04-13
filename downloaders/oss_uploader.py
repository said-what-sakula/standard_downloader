"""
downloaders/oss_uploader.py
将本地文件上传到 OSS，接口格式与 patent-crawler 保持一致。
"""

import json
import os
import time

import requests

from .config import get_storage_config


def _content_type(ext: str) -> str:
    mapping = {
        ".pdf":  "application/pdf",
        ".doc":  "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls":  "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".txt":  "text/plain",
    }
    return mapping.get(ext.lower(), "application/octet-stream")


def upload_to_oss(local_path: str, filename: str) -> dict:
    """
    上传本地文件到 OSS。

    请求体字段（与 patent-crawler 保持一致）：
      path       = bucket_path（存储子目录，如 "test"）
      bucketName = bucket_name
      isRename   = "true"（服务端自动重命名，避免冲突）
    files: {'file': (basename, fh, mime)}

    返回 {"oss_path": str, "oss_url": str}，失败返回 {}。
    重试策略：5 次，超时逐步递增（60/120/180/240/300 秒），间隔 5/10/15/20 秒。
    """
    cfg = get_storage_config()
    upload_url  = cfg.get("upload_url", "")
    save_base   = cfg.get("save_path", "").rstrip("/")
    bucket_name = cfg.get("bucket_name", "")
    bucket_path = cfg.get("bucket_path", "")

    if not upload_url:
        return {}

    ext  = os.path.splitext(filename)[1]
    mime = _content_type(ext)

    timeouts = [60, 120, 180, 240, 300]
    for attempt, timeout in enumerate(timeouts, start=1):
        try:
            with open(local_path, "rb") as fh:
                resp = requests.post(
                    upload_url,
                    data={
                        "path":       bucket_path,
                        "bucketName": bucket_name,
                        "isRename":   "true",
                    },
                    files={"file": (os.path.basename(filename), fh, mime)},
                    timeout=timeout,
                )
            resp.raise_for_status()
            result = resp.json()
            data = result.get("data") or {}
            if isinstance(data, str):
                data = json.loads(data) or {}
            oss_path = data.get("downloadFilePath", "")
            oss_url  = f"{save_base}/{oss_path.lstrip('/')}" if oss_path else ""
            if oss_path:
                return {"oss_path": oss_path, "oss_url": oss_url}
            return {}
        except Exception as e:
            print(f"[OSS] 上传失败 第{attempt}次 [{os.path.basename(filename)}]: {e}",
                  flush=True)
            if attempt < len(timeouts):
                time.sleep(5 * attempt)

    print(f"[OSS] 已重试 {len(timeouts)} 次，放弃上传: {filename}", flush=True)
    return {}

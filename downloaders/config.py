"""
downloaders/config.py
下载器子进程的配置加载——读取项目根目录的 config.json。
"""

import json
from functools import lru_cache
from pathlib import Path

_BASE = Path(__file__).parent.parent


@lru_cache(maxsize=1)
def _load_config() -> dict:
    cfg_file = _BASE / "config.json"
    if cfg_file.exists():
        with open(cfg_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_storage_config() -> dict:
    """返回 config.json 中的 storage 节，缺失时返回空字典。"""
    return _load_config().get("storage", {})


def get_db_config() -> dict:
    """返回 config.json 中的 database 节，缺失时返回空字典。"""
    return _load_config().get("database", {})

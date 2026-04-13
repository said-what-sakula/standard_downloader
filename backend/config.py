"""
backend/config.py
配置管理：config.json（服务器设置）+ 来源列表（MySQL）
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_JSON = PROJECT_ROOT / "config.json"

_DEFAULT_CONFIG = {
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
        "log_dir": "logs",
    },
    "chromium_path": "",
}


# ── config.json ──────────────────────────────────────────────────────────────

def load() -> dict:
    if CONFIG_JSON.exists():
        with open(CONFIG_JSON, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in _DEFAULT_CONFIG.items():
            data.setdefault(k, v)
        return data
    return dict(_DEFAULT_CONFIG)


def save(data: dict) -> None:
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_dir() -> Path:
    cfg = load()
    p = Path(cfg["server"].get("log_dir", "logs"))
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── sources（MySQL）──────────────────────────────────────────────────────────

def load_sources() -> list[dict]:
    """从 MySQL 读取来源列表。"""
    from downloaders.db import get_all_sources
    return get_all_sources()


def save_sources(sources: list[dict]) -> None:
    """将来源列表写入 MySQL（全量替换）。"""
    from downloaders.db import replace_all_sources
    replace_all_sources(sources)


def make_source_id(name: str) -> str:
    """将来源名称转换为合法的文件/日志 ID（保留中文，替换特殊字符）"""
    return re.sub(r'[/\\:*?"<>|\s]', "_", name)

"""
downloaders/common.py
共用工具：BaseDownloader 模板基类、DownloadRecorder、文件工具、should_stop。
"""

import os
import re
import time
import base64
import signal
import tempfile
import threading
import traceback
from typing import Optional
from urllib.parse import urljoin
from pathlib import Path

from playwright.sync_api import Playwright, Page, BrowserContext, Download

try:
    import ddddocr
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠ 未安装 ddddocr，请运行：pip install ddddocr")


# ══════════════════════════════════════════════
#  常量
# ══════════════════════════════════════════════

_BASE = Path(__file__).parent.parent
LOG_DIR = _BASE / "logs"

# Chromium 路径解析优先级：
#   1. 环境变量 CHROMIUM_PATH（服务器部署时设置）
#   2. config.json 中的 chromium_path 字段（本地开发 / 前端界面配置）
#   3. None → Playwright 使用自己安装的 Chromium


def resolve_chromium_path() -> Optional[str]:
    """
    动态解析 Chromium 可执行文件路径。
    返回 None 时 Playwright 会自动使用其内置的 Chromium。
    """
    # 1. 环境变量优先（服务器部署场景）
    env_path = os.environ.get("CHROMIUM_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path

    # 2. 读取 config.json（本地开发或前端界面配置）
    try:
        import json
        cfg_file = _BASE / "config.json"
        if cfg_file.exists():
            with open(cfg_file, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg_path = cfg.get("chromium_path", "").strip()
            if cfg_path and Path(cfg_path).exists():
                return cfg_path
    except Exception:
        pass

    # 3. 让 Playwright 自动检测（服务器上执行过 playwright install chromium 后生效）
    return None


# ══════════════════════════════════════════════
#  优雅停止机制
# ══════════════════════════════════════════════

_stop_latched: dict[str, bool] = {}
_stop_lock = threading.Lock()


def should_stop(source_id: str) -> bool:
    """
    检查优雅停止标志文件（logs/{source_id}.stop）。
    首次检测到后删除文件并设置内存 latch，后续调用直接读 latch。
    """
    with _stop_lock:
        if _stop_latched.get(source_id):
            return True
    flag = LOG_DIR / f"{source_id}.stop"
    if flag.exists():
        try:
            flag.unlink()
        except Exception:
            pass
        with _stop_lock:
            _stop_latched[source_id] = True
        print(f"[Stop] 收到停止信号，当前任务完成后退出", flush=True)
        return True
    return False


def setup_stop_signal(source_id: str):
    """
    设置 SIGINT（Ctrl+C）和 SIGTERM 信号处理器。
    收到信号时创建 stop 标志文件，让 should_stop() 检测到后
    等当前下载完成再退出（优雅退出）。
    """
    def _handler(sig, frame):
        print(f"\n[Signal] 收到停止信号，等待当前下载完成后退出...", flush=True)
        flag = LOG_DIR / f"{source_id}.stop"
        try:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.touch()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (OSError, ValueError, AttributeError):
        pass  # Windows 某些情况下不支持 SIGTERM


# ══════════════════════════════════════════════
#  下载记录（断点续传，纯 MySQL）
# ══════════════════════════════════════════════

class DownloadRecorder:
    """
    下载进度记录器，使用 MySQL 作为唯一存储。
    启动时从数据库加载已有状态，避免重复下载。
    数据库未配置时内存缓存仍正常工作（重启后会重新爬取）。
    """

    def __init__(self, source_type: str = ""):
        self.source_type = source_type  # guobiao / hangbiao
        # 内存缓存：std_no -> status，启动时从 DB 加载
        self._cache: dict[str, str] = {}

    def load_from_db(self, source_name: str) -> None:
        """从 MySQL 加载指定来源的所有记录状态到内存缓存（断点续传用）。"""
        try:
            from .db import get_engine
            from sqlalchemy import text as sql_text
            engine = get_engine()
            if engine is None:
                return
            with engine.connect() as conn:
                rows = conn.execute(
                    sql_text(
                        "SELECT std_no, status FROM standard_download_record "
                        "WHERE source_name = :s"
                    ),
                    {"s": source_name},
                ).fetchall()
            for r in rows:
                self._cache[r[0]] = r[1]
            print(f"[Recorder] 已从 DB 加载 {len(self._cache)} 条记录（{source_name}）", flush=True)
        except Exception as e:
            print(f"[Recorder] 加载历史记录失败：{e}", flush=True)

    def get_status(self, std_no: str) -> Optional[str]:
        return self._cache.get(std_no)

    def is_done(self, std_no: str) -> bool:
        return self.get_status(std_no) == "SUCCESS"

    def save(self, std_no: str, std_name: str, source: str, status: str,
             oss_url: str = None, oss_path: str = None, local_path: str = None):
        """写入 MySQL，同时更新内存缓存。数据库未配置时静默跳过。"""
        self._cache[std_no] = status
        try:
            from .db import upsert_std_record
            upsert_std_record(std_no, std_name, source, self.source_type,
                              status, oss_url, oss_path, local_path)
        except Exception as e:
            print(f"   ⚠ DB 记录失败：{e}", flush=True)


# ══════════════════════════════════════════════
#  浏览器工厂
# ══════════════════════════════════════════════

def create_browser_and_context(playwright: Playwright):
    chromium_path = resolve_chromium_path()
    if chromium_path:
        print(f"[Browser] 使用 Chromium: {chromium_path}", flush=True)
    else:
        print("[Browser] 使用 Playwright 内置 Chromium", flush=True)
    browser = playwright.chromium.launch(
        executable_path=chromium_path,   # None = Playwright 自动检测
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 1920, "height": 1080},
    )
    return browser, context


# ══════════════════════════════════════════════
#  文件保存工具
# ══════════════════════════════════════════════

def sanitize(s: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "_", s)


def _make_filename(download: Download, std_no: str, std_name: str) -> tuple[str, str]:
    """返回 (orig_filename, new_filename)，new_filename 按 '标准号 标准名称.ext' 命名。"""
    orig = download.suggested_filename or f"{std_no}.pdf"
    ext = os.path.splitext(orig)[1] or ".pdf"
    base = f"{sanitize(std_no)} {sanitize(std_name)}"
    if len(base) + len(ext) > 200:
        base = base[: 200 - len(ext)]
    return orig, base + ext


def save_and_rename(download: Download, download_dir: str, std_no: str, std_name: str) -> str:
    """
    将下载文件保存到系统临时目录，并按 '标准号 标准名称.ext' 重命名。
    用于 handle_download() 内部，也保留供直接调用（向后兼容）。
    """
    orig, new_name = _make_filename(download, std_no, std_name)

    tmp_dir = tempfile.mkdtemp(prefix="std_dl_")
    tmp_path = os.path.join(tmp_dir, orig)
    new_path = os.path.join(tmp_dir, new_name)

    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    download.save_as(tmp_path)
    if tmp_path != new_path:
        if os.path.exists(new_path):
            os.remove(new_path)
        os.rename(tmp_path, new_path)
    print(f"   ✓ 临时保存：{new_name}", flush=True)
    return new_path


def try_upload_oss(local_path: str, source_type: str) -> dict:
    """
    尝试将本地文件上传到 OSS。
    OSS 路径格式：standard/{source_type}/{filename}
    storage.upload_url 未配置时直接返回 {}，不影响主流程。
    """
    try:
        from .oss_uploader import upload_to_oss
        filename = f"standard/{source_type}/{os.path.basename(local_path)}"
        result = upload_to_oss(local_path, filename)
        if result.get("oss_url"):
            print(f"   ✓ OSS：{result['oss_url']}", flush=True)
        return result
    except Exception as e:
        print(f"   ⚠ OSS 上传出错：{e}", flush=True)
        return {}


def finalize_temp(tmp_path: str, download_dir: str, source_type: str) -> dict:
    """
    将已保存在临时目录的文件根据 storage.mode 进行最终处理。
    适用于需要先验证文件有效性（如行标 PDF 检查）再决定存储方式的场景。

    mode:
      "local" — 移动到 download_dir，不上传 OSS
      "oss"   — 上传 OSS，删除临时文件（默认）
      "both"  — 移动到 download_dir，同时上传 OSS

    返回 dict，包含部分或全部字段：local_path, oss_url, oss_path
    """
    from .config import get_storage_config
    mode = get_storage_config().get("mode", "oss")
    filename = os.path.basename(tmp_path)

    if mode == "local":
        os.makedirs(download_dir, exist_ok=True)
        dest = os.path.join(download_dir, filename)
        if os.path.exists(dest):
            os.remove(dest)
        os.rename(tmp_path, dest)
        # 清理空的临时目录
        try:
            tmp_dir = os.path.dirname(tmp_path)
            if os.path.basename(tmp_dir).startswith("std_dl_"):
                os.rmdir(tmp_dir)
        except OSError:
            pass
        print(f"   ✓ 本地保存：{dest}", flush=True)
        return {"local_path": dest}

    if mode == "both":
        os.makedirs(download_dir, exist_ok=True)
        dest = os.path.join(download_dir, filename)
        if os.path.exists(dest):
            os.remove(dest)
        os.rename(tmp_path, dest)
        try:
            tmp_dir = os.path.dirname(tmp_path)
            if os.path.basename(tmp_dir).startswith("std_dl_"):
                os.rmdir(tmp_dir)
        except OSError:
            pass
        print(f"   ✓ 本地保存：{dest}", flush=True)
        oss = try_upload_oss(dest, source_type)
        return {"local_path": dest, **oss}

    # 默认 mode == "oss"
    oss = try_upload_oss(tmp_path, source_type)
    remove_temp_file(tmp_path)
    return oss


def handle_download(
    download: Download,
    download_dir: str,
    std_no: str,
    std_name: str,
    source_type: str,
) -> dict:
    """
    根据 config.json storage.mode 决定存储策略，返回 recorder.save 需要的字段。

    mode:
      "local" — 保存到 download_dir，不上传 OSS
      "oss"   — 保存到临时目录，上传 OSS，删除临时文件（默认）
      "both"  — 保存到 download_dir，同时上传 OSS

    返回 dict，包含部分或全部字段：local_path, oss_url, oss_path
    """
    from .config import get_storage_config
    mode = get_storage_config().get("mode", "oss")

    _, new_name = _make_filename(download, std_no, std_name)

    if mode == "local":
        os.makedirs(download_dir, exist_ok=True)
        dest = os.path.join(download_dir, new_name)
        if os.path.exists(dest):
            os.remove(dest)
        download.save_as(dest)
        print(f"   ✓ 本地保存：{dest}", flush=True)
        return {"local_path": dest}

    if mode == "both":
        os.makedirs(download_dir, exist_ok=True)
        dest = os.path.join(download_dir, new_name)
        if os.path.exists(dest):
            os.remove(dest)
        download.save_as(dest)
        print(f"   ✓ 本地保存：{dest}", flush=True)
        oss = try_upload_oss(dest, source_type)
        return {"local_path": dest, **oss}

    # 默认 mode == "oss"
    tmp = save_and_rename(download, download_dir, std_no, std_name)
    oss = try_upload_oss(tmp, source_type)
    remove_temp_file(tmp)
    return oss


def is_valid_pdf(path: str, min_size: int = 1024) -> bool:
    """检查文件是否为有效 PDF（至少 1KB 且以 %PDF 开头）。"""
    try:
        size = os.path.getsize(path)
        if size < min_size:
            return False
        with open(path, "rb") as f:
            header = f.read(5)
        return header.startswith(b"%PDF-")
    except Exception:
        return False


def remove_temp_file(path: str) -> None:
    """删除 save_and_rename 创建的临时文件及其临时目录（前缀 std_dl_）。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
        tmp_dir = os.path.dirname(path) if path else ""
        if tmp_dir and os.path.basename(tmp_dir).startswith("std_dl_"):
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass  # 目录非空时忽略
    except Exception:
        pass


# ══════════════════════════════════════════════
#  基类：BaseDownloader（模板方法）
# ══════════════════════════════════════════════

class BaseDownloader:
    """
    子类需实现：
      _list_page_tag()   → URL 中代表列表页的特征字符串
      _build_page_url()  → 构造第 N 页 URL
      _parse_rows()      → 解析列表页行
      _download_one()    → 处理单条标准
      _go_next_page()    → 翻到下一页，返回 False 表示已是最后页
    """

    def __init__(self, context: BrowserContext, recorder: DownloadRecorder, source_id: str = ""):
        self.context = context
        self.recorder = recorder
        self.source_id = source_id  # 用于 should_stop() 检查

    # ── 子类必须实现 ──────────────────────────────────────────────────────

    def _list_page_tag(self) -> str:
        raise NotImplementedError

    def _build_page_url(self, base_url: str, page_num: int) -> str:
        raise NotImplementedError

    def _parse_rows(self, page: Page) -> list[dict]:
        raise NotImplementedError

    def _download_one(self, row: dict, download_dir: str, source_name: str, list_page: Page = None) -> bool:
        raise NotImplementedError

    def _go_next_page(self, page: Page) -> bool:
        raise NotImplementedError

    # ── 模板方法：主下载流程 ──────────────────────────────────────────────

    def download_source(self, source: dict, list_page: Page):
        name = source["name"]
        url = source["url"]
        download_dir = source.get("download_dir", os.path.join("download", name))
        os.makedirs(download_dir, exist_ok=True)

        page_num = 1
        any_new_in_session = False  # 本次会话是否已遇到过未处理条目（会话级标记）
        print(f"\n{'═' * 50}", flush=True)
        print(f"▶ 来源：[{source.get('type', 'guobiao')}] {name}", flush=True)
        print(f"  URL：{url}", flush=True)
        self._nav(list_page, self._build_page_url(url, page_num))

        while True:
            # 检查停止信号
            if self.source_id and should_stop(self.source_id):
                print(f"  ⏹ 收到停止信号，已停止 [{name}]", flush=True)
                break

            page_reloaded = False
            all_skipped   = True   # 本页全部已处理则为 True
            rows = self._parse_rows(list_page)

            for row in rows:
                # 每行处理前也检查停止信号
                if self.source_id and should_stop(self.source_id):
                    print(f"  ⏹ 收到停止信号，已停止 [{name}]", flush=True)
                    return

                std_no = row.get("std_no", "")
                std_name = row.get("std_name", "")

                status = self.recorder.get_status(std_no)
                if status in ("SUCCESS", "NO_FULL_TEXT", "ABOLISHED", "ADOPTED"):
                    print(f"  ✔ 跳过({status})：{std_no}", flush=True)
                    continue

                all_skipped = False
                print(f"  → {std_no}  {std_name}", flush=True)
                cache_size_before = len(self.recorder._cache)
                try:
                    self._download_one(row, download_dir, name, list_page)
                except Exception as e:
                    print(f"  ⚠ 处理 {std_no} 出错：{e}", flush=True)
                    print(traceback.format_exc(), flush=True)
                finally:
                    # 只有实际下载成功（SUCCESS）才触发增量边界标记；
                    # NO_FULL_TEXT / ABOLISHED 等非成功状态不触发，
                    # 避免验证码失败等临时问题导致假增量边界、提前退出。
                    if len(self.recorder._cache) > cache_size_before:
                        new_status = self.recorder.get_status(std_no)
                        if new_status == "SUCCESS":
                            any_new_in_session = True
                    if self._ensure_list_page(list_page, url, page_num):
                        page_reloaded = True
                        break

            if page_reloaded:
                print("  ⚠ 列表页已重置，重新扫描当前页...", flush=True)
                continue

            # 增量优化：整页全部已处理，且本次会话已成功下载过新文件，说明已到增量边界。
            # DOWNLOADER_FULL_SCAN=1 时跳过增量早停（控制台手动启动为全量扫描）。
            if all_skipped and rows and any_new_in_session:
                if os.environ.get("DOWNLOADER_FULL_SCAN") == "1":
                    print(f"  ⏩ 本页全部已处理，全量模式继续扫描", flush=True)
                else:
                    print(f"  ✅ 本页全部已处理，增量完成【{name}】", flush=True)
                    break

            if self._go_next_page(list_page):
                page_num += 1
            else:
                print(f"  已到最后一页，【{name}】下载完成", flush=True)
                break

    # ── 共用工具 ──────────────────────────────────────────────────────────

    def _nav(self, page: Page, url: str, timeout: int = 15000):
        page.goto(url)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass
        time.sleep(2)

    def _open_page(self, url: str) -> Page:
        p = self.context.new_page()
        try:
            p.goto(url)
            try:
                p.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            time.sleep(1)
            return p
        except Exception:
            try:
                p.close()
            except Exception:
                pass
            raise

    def _ensure_list_page(self, page: Page, url: str, page_num: int) -> bool:
        try:
            if self._list_page_tag() in page.url:
                return False
            self._nav(page, self._build_page_url(url, page_num))
            return True
        except Exception:
            try:
                self._nav(page, url)
            except Exception:
                pass
            return True

    def _close_pages(self, *pages):
        for pg in set(p for p in pages if p is not None):
            try:
                pg.close()
            except Exception:
                pass

    def _wait_download(self, bucket: list, timeout: int = 30) -> Optional[Download]:
        start = time.time()
        while not bucket and time.time() - start < timeout:
            time.sleep(0.4)
        return bucket[0] if bucket else None

    def _ocr(self, image_bytes: bytes) -> str:
        if not OCR_AVAILABLE or not image_bytes:
            return ""
        try:
            ocr = ddddocr.DdddOcr(show_ad=False)
            raw = ocr.classification(image_bytes)
            return "".join(c for c in raw if c.isalnum())[:4]
        except Exception:
            return ""

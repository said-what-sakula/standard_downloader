"""
backend/process_manager.py
下载器子进程管理：启动、停止、SSE 日志广播、状态查询。

每个来源（MySQL download_source 表中的一项）对应一个 DownloaderProcess 实例。
子进程通过环境变量获取配置，stdout 被捕获后写日志文件并广播到 SSE 队列。
"""

import asyncio
import datetime
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from . import config as cfg

_BASE = Path(__file__).parent.parent

# ── 脚本模块映射 ───────────────────────────────────────────────────────────────
_TYPE_MODULE = {
    "guobiao":  "downloaders.guobiao",
    "hangbiao": "downloaders.hangbiao",
}


# ── DownloaderProcess ─────────────────────────────────────────────────────────

class DownloaderProcess:
    """管理单个来源的下载子进程 + SSE 日志广播"""

    def __init__(self, source: dict):
        self.source_id: str = cfg.make_source_id(source["name"])
        self.source: dict = source          # {name, type, url, ...}
        self._proc: Optional[object] = None  # subprocess.Popen
        self._sse_queues: list[asyncio.Queue] = []
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.start_time: Optional[datetime.datetime] = None
        self.exit_code: Optional[int] = None
        self.log_path: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, full_scan: bool = True) -> bool:
        """启动下载子进程；已在运行则返回 False。
        full_scan=True（控制台手动启动）跳过增量早停，全量扫描；
        full_scan=False（定时任务）启用增量早停。
        """
        import subprocess

        if self.is_running:
            return False

        src_type = self.source.get("type", "guobiao")
        module = _TYPE_MODULE.get(src_type)
        if not module:
            print(f"[process_manager] 未知类型 '{src_type}'", flush=True)
            return False

        name = self.source["name"]
        download_dir = str(_BASE / "download" / name)

        self.start_time = datetime.datetime.now()
        self.exit_code = None

        log_date = self.start_time.strftime("%Y%m%d")
        log_filename = f"{self.source_id}_{log_date}.log"
        self.log_path = str(cfg.log_dir() / log_filename)

        env = os.environ.copy()
        env.update({
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "DOWNLOADER_SOURCE_NAME": name,
            "DOWNLOADER_SOURCE_URL":  self.source["url"],
            "DOWNLOADER_SOURCE_TYPE": src_type,
            "DOWNLOADER_SOURCE_ID":   self.source_id,
            "DOWNLOADER_DOWNLOAD_DIR": download_dir,
            "DOWNLOADER_FULL_SCAN": "1" if full_scan else "0",
        })

        self._proc = subprocess.Popen(
            [sys.executable, "-m", module],
            cwd=str(_BASE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        threading.Thread(target=self._stdout_reader, daemon=True).start()
        return True

    def stop(self) -> bool:
        """优雅停止：写停止标志文件，5 分钟后强制终止"""
        if not self.is_running:
            return False

        flag = cfg.log_dir() / f"{self.source_id}.stop"
        try:
            flag.write_text("stop", encoding="utf-8")
        except Exception as e:
            print(f"[process_manager] 写停止标志失败: {e}", flush=True)

        threading.Thread(
            target=self._force_kill_after_timeout,
            args=(300,),
            daemon=True,
        ).start()
        return True

    def _force_kill_after_timeout(self, timeout: int) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_running:
                return
            time.sleep(2)
        self._force_kill()

    def _force_kill(self) -> None:
        if not self.is_running:
            return
        pid = self._proc.pid
        if sys.platform == "win32":
            import subprocess
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    check=False, capture_output=True,
                )
            except Exception:
                self._proc.kill()
        else:
            import signal
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except Exception:
                self._proc.kill()

    def subscribe_sse(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._sse_queues.append(q)
        return q

    def unsubscribe_sse(self, q: asyncio.Queue) -> None:
        with self._lock:
            try:
                self._sse_queues.remove(q)
            except ValueError:
                pass

    def _broadcast(self, line: str) -> None:
        with self._lock:
            queues = list(self._sse_queues)
        for q in queues:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(q.put_nowait, line)

    def _stdout_reader(self) -> None:
        separator = (
            f"\n{'=' * 60}\n"
            f"[Run Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}]  "
            f"[{self.source['name']}]\n"
            f"{'=' * 60}\n"
        )
        try:
            with open(self.log_path, "a", encoding="utf-8") as lf:
                lf.write(separator)
                lf.flush()
                for line in self._proc.stdout:
                    lf.write(line)
                    lf.flush()
                    self._broadcast(line.rstrip("\n"))
        except Exception as e:
            self._broadcast(f"[process_manager] stdout reader error: {e}")
        finally:
            self._proc.wait()
            self.exit_code = self._proc.returncode
            self._broadcast("__EOF__")

    def status(self) -> dict:
        # 从 MySQL 查询该来源的记录数；数据库未配置时降级为 CSV 计数
        downloaded = _count_downloaded(self.source["name"])

        return {
            "id":          self.source_id,
            "name":        self.source["name"],
            "type":        self.source.get("type", "guobiao"),
            "url":         self.source["url"],
            "running":     self.is_running,
            "start_time":  self.start_time.isoformat() if self.start_time else None,
            "exit_code":   self.exit_code,
            "log_path":    self.log_path,
            "downloaded":  downloaded,
        }


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _count_downloaded(source_name: str) -> int:
    """从 MySQL 查询该来源的记录数。数据库未配置时返回 0。"""
    try:
        from downloaders.db import count_records_by_source
        return count_records_by_source(source_name)
    except Exception:
        return 0


# ── 全局进程注册表（按需动态加载）────────────────────────────────────────────

_processes: dict[str, DownloaderProcess] = {}
_processes_lock = threading.Lock()


def reload_registry() -> None:
    """从 MySQL 重新加载来源，补充新来源（不删除已运行的旧来源）"""
    sources = cfg.load_sources()
    with _processes_lock:
        for src in sources:
            sid = cfg.make_source_id(src["name"])
            if sid not in _processes:
                _processes[sid] = DownloaderProcess(src)
            else:
                # 更新来源信息（不影响运行中的进程）
                _processes[sid].source = src


def get_process(source_id: str) -> DownloaderProcess:
    with _processes_lock:
        if source_id not in _processes:
            raise KeyError(f"Unknown source_id: {source_id}")
        return _processes[source_id]


def all_statuses() -> list[dict]:
    with _processes_lock:
        procs = list(_processes.values())
    return [p.status() for p in procs]

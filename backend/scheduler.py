"""
backend/scheduler.py
APScheduler 定时任务：支持 Cron 和 Interval 两种触发方式，持久化到 MySQL。
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR


# ── 上次执行结果（内存缓存，重启清空） ────────────────────────────────────────
_last_run: dict[str, dict] = {}


def _job_listener(event) -> None:
    exc = getattr(event, "exception", None)
    _last_run[event.job_id] = {
        "time":    event.scheduled_run_time.isoformat(),
        "success": exc is None,
        "error":   str(exc) if exc else None,
    }


# ── Jobstore ──────────────────────────────────────────────────────────────────

def _make_jobstore():
    """从 config.json 读取数据库配置，构造 MySQL jobstore；未配置时返回 None（内存存储）。"""
    try:
        from downloaders.config import get_db_config
        cfg = get_db_config()
        if cfg.get("host"):
            url = (
                f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
                f"@{cfg['host']}:{cfg['port']}/{cfg['db']}"
                f"?charset=utf8mb4"
            )
            return SQLAlchemyJobStore(url=url)
    except Exception:
        pass
    return None


_jobstore = _make_jobstore()
_scheduler = AsyncIOScheduler(
    jobstores={"default": _jobstore} if _jobstore else {},
    job_defaults={"misfire_grace_time": 60},
    timezone="Asia/Shanghai",
)
_scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)


# ── 生命周期 ──────────────────────────────────────────────────────────────────

def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


def start():
    if not _scheduler.running:
        _scheduler.start()


def shutdown():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


# ── 任务执行体 ─────────────────────────────────────────────────────────────────

def _downloader_job(source_id: str):
    """定时触发：若未在运行则启动对应下载进程"""
    from .process_manager import get_process, reload_registry
    reload_registry()
    try:
        proc = get_process(source_id)
        if not proc.is_running:
            proc.start(full_scan=False)
    except KeyError:
        print(f"[scheduler] 找不到 source_id={source_id}，跳过", flush=True)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_job(source_id: str, trigger_type: str, **kwargs) -> dict:
    """
    trigger_type: "cron" | "interval"
    cron kwargs:     hour, minute, day_of_week ...
    interval kwargs: hours, minutes, seconds ...
    """
    if trigger_type == "cron":
        trigger = CronTrigger(**kwargs)
    elif trigger_type == "interval":
        trigger = IntervalTrigger(**kwargs)
    else:
        raise ValueError(f"Unknown trigger_type: {trigger_type}")

    job = _scheduler.add_job(
        _downloader_job,
        trigger=trigger,
        args=[source_id],
        replace_existing=False,
    )
    return _job_to_dict(job)


def remove_job(job_id: str) -> bool:
    try:
        _scheduler.remove_job(job_id)
        return True
    except Exception:
        return False


def pause_job(job_id: str) -> bool:
    try:
        _scheduler.pause_job(job_id)
        return True
    except Exception:
        return False


def resume_job(job_id: str) -> bool:
    try:
        _scheduler.resume_job(job_id)
        return True
    except Exception:
        return False


def list_jobs() -> list:
    return [_job_to_dict(j) for j in _scheduler.get_jobs()]


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _format_trigger(job) -> str:
    """将 APScheduler trigger 对象转换为可读中文字符串。"""
    trigger = job.trigger
    cls = type(trigger).__name__

    if cls == "CronTrigger":
        fields = {f.name: str(f) for f in trigger.fields if not f.is_default}
        hour   = fields.get("hour",   "*")
        minute = fields.get("minute", "0")
        minute_str = minute.zfill(2) if minute.isdigit() else minute
        dow = fields.get("day_of_week")
        if dow:
            return f"每周 {dow}  {hour}:{minute_str}"
        return f"每天 {hour}:{minute_str}"

    if cls == "IntervalTrigger":
        secs = int(trigger.interval.total_seconds())
        h, rem = divmod(secs, 3600)
        m = rem // 60
        if h and m:
            return f"每 {h} 小时 {m} 分钟"
        if h:
            return f"每 {h} 小时"
        return f"每 {m} 分钟"

    return str(trigger)


def _job_to_dict(job) -> dict:
    lr = _last_run.get(job.id)
    return {
        "id":        job.id,
        "source_id": job.args[0] if job.args else None,
        "trigger":   _format_trigger(job),
        "next_run":  job.next_run_time.isoformat() if job.next_run_time else None,
        "paused":    job.next_run_time is None,
        "last_run":  lr,
    }

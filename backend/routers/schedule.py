"""
backend/routers/schedule.py
定时任务 API：列表、创建、删除、暂停、恢复。
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import scheduler as sch

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


class JobCreate(BaseModel):
    source_id:    str
    trigger_type: str           # "cron" | "interval"
    # cron 参数
    hour:         Optional[str] = None
    minute:       Optional[str] = None
    day_of_week:  Optional[str] = None
    # interval 参数
    hours:        Optional[int] = None
    minutes:      Optional[int] = None
    seconds:      Optional[int] = None


@router.get("")
def list_jobs():
    return sch.list_jobs()


@router.post("")
def create_job(body: JobCreate):
    kwargs: dict = {}
    if body.trigger_type == "cron":
        if body.hour is not None:
            kwargs["hour"] = body.hour
        if body.minute is not None:
            kwargs["minute"] = body.minute
        if body.day_of_week is not None:
            kwargs["day_of_week"] = body.day_of_week
    elif body.trigger_type == "interval":
        if body.hours is not None:
            kwargs["hours"] = body.hours
        if body.minutes is not None:
            kwargs["minutes"] = body.minutes
        if body.seconds is not None:
            kwargs["seconds"] = body.seconds
    else:
        raise HTTPException(status_code=422, detail="trigger_type 须为 cron 或 interval")

    try:
        job = sch.add_job(body.source_id, body.trigger_type, **kwargs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return job


@router.delete("/{job_id}")
def delete_job(job_id: str):
    ok = sch.remove_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@router.post("/{job_id}/pause")
def pause_job(job_id: str):
    ok = sch.pause_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@router.post("/{job_id}/resume")
def resume_job(job_id: str):
    ok = sch.resume_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}

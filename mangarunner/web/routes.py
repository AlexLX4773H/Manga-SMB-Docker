import os
import math
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import humanize
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from mangarunner.config import load_config
from mangarunner.db.database import get_db_session
from mangarunner.db import crud
from mangarunner.engine.script_registry import get_registered_scripts, get_scripts_by_category, get_script_by_id
from mangarunner.engine.queue_manager import QueueManager

router = APIRouter(include_in_schema=False)

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))
static_dir = Path(__file__).parent / "static"

def format_bytes(b: Optional[int]) -> str:
    if not b:
        return "0 B"
    return humanize.naturalsize(b, binary=True)

def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    total = int(seconds)
    if total < 60:
        return f"{seconds:.1f}s"
    mins = total // 60
    secs = total % 60
    return f"{mins}m {secs}s"

def format_datetime(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def time_ago(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return humanize.naturaltime(now - dt)

templates.env.filters["format_bytes"] = format_bytes
templates.env.filters["format_duration"] = format_duration
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["time_ago"] = time_ago

@router.get("/favicon.ico")
def favicon_route():
    fav_path = static_dir / "favicon.ico"
    if fav_path.exists():
        return FileResponse(str(fav_path), media_type="image/x-icon")
    icon_path = static_dir / "icon.png"
    if icon_path.exists():
        return FileResponse(str(icon_path), media_type="image/png")
    raise HTTPException(status_code=404)

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request, session: Session = Depends(get_db_session)):
    stats = crud.get_stats(session)
    recent_runs = crud.get_runs(session, limit=8)
    
    processed_runs = []
    for r in recent_runs:
        reps = []
        if r.reports_json:
            try:
                reps = json.loads(r.reports_json)
            except Exception:
                pass
        processed_runs.append({
            "run_id": r.run_id,
            "script_name": r.script_name,
            "category": r.category,
            "status": r.status,
            "dry_run": r.dry_run,
            "enqueued_at": r.enqueued_at,
            "duration_seconds": r.duration_seconds,
            "reports": reps,
        })

    cfg = load_config()
    rep_dir = Path(cfg.reports_dir)
    recent_reports = []
    if rep_dir.exists():
        for f in rep_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".xlsx", ".txt", ".csv"):
                stat = f.stat()
                recent_reports.append({
                    "name": f.name,
                    "ext": f.suffix.lower(),
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                })
    recent_reports.sort(key=lambda x: x["mtime"], reverse=True)
    recent_reports = recent_reports[:6]

    qm = QueueManager.get_instance()
    queue_status = await qm.get_queue_status()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_tab": "dashboard",
            "stats": stats,
            "recent_runs": processed_runs,
            "recent_reports": recent_reports,
            "queue_status": queue_status,
            "total_scripts": len(get_registered_scripts()),
            "manga_root": cfg.manga_root,
        },
    )

@router.get("/scripts", response_class=HTMLResponse)
def scripts_page(request: Request):
    categories = get_scripts_by_category()
    cfg = load_config()
    return templates.TemplateResponse(
        request=request,
        name="scripts.html",
        context={
            "active_tab": "scripts",
            "categories": categories,
            "total_scripts": len(get_registered_scripts()),
            "manga_root": cfg.manga_root,
        },
    )

@router.get("/active", response_class=HTMLResponse)
async def active_run_page(request: Request):
    qm = QueueManager.get_instance()
    queue_status = await qm.get_queue_status()
    cfg = load_config()

    return templates.TemplateResponse(
        request=request,
        name="active.html",
        context={
            "active_tab": "active",
            "queue_status": queue_status,
            "manga_root": cfg.manga_root,
        },
    )

@router.get("/runs", response_class=HTMLResponse)
def runs_history_page(
    request: Request,
    page: int = Query(1, ge=1),
    status: Optional[str] = None,
    category: Optional[str] = None,
    session: Session = Depends(get_db_session),
):
    page_size = 25
    offset = (page - 1) * page_size
    runs = crud.get_runs(session, limit=page_size, offset=offset, status=status, category=category)
    total_count = crud.count_runs(session, status=status)
    total_pages = max(1, math.ceil(total_count / page_size))

    processed_runs = []
    for r in runs:
        reps = []
        if r.reports_json:
            try:
                reps = json.loads(r.reports_json)
            except Exception:
                pass
        processed_runs.append({
            "run_id": r.run_id,
            "script_name": r.script_name,
            "category": r.category,
            "status": r.status,
            "dry_run": r.dry_run,
            "enqueued_at": r.enqueued_at,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "duration_seconds": r.duration_seconds,
            "exit_code": r.exit_code,
            "reports": reps,
            "error_message": r.error_message,
        })

    return templates.TemplateResponse(
        request=request,
        name="runs.html",
        context={
            "active_tab": "runs",
            "runs": processed_runs,
            "total_count": total_count,
            "current_page": page,
            "total_pages": total_pages,
            "filter_status": status or "",
            "filter_category": category or "",
        },
    )

@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail_page(run_id: str, request: Request, session: Session = Depends(get_db_session)):
    run = crud.get_job_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    reports = []
    if run.reports_json:
        try:
            reports = json.loads(run.reports_json)
        except Exception:
            pass

    log_content = ""
    if run.log_file and os.path.exists(run.log_file):
        try:
            with open(run.log_file, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
        except Exception as e:
            log_content = f"Error reading log file: {e}"

    return templates.TemplateResponse(
        request=request,
        name="run_detail.html",
        context={
            "active_tab": "runs",
            "run": run,
            "reports": reports,
            "log_content": log_content,
        },
    )

@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    cfg = load_config()
    rep_dir = Path(cfg.reports_dir)
    reports = []
    
    if rep_dir.exists():
        for f in rep_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".xlsx", ".xls", ".txt", ".csv", ".log"):
                stat = f.stat()
                ext = f.suffix.lower()
                reports.append({
                    "name": f.name,
                    "extension": ext,
                    "file_type": "excel" if ext in (".xlsx", ".xls") else ("csv" if ext == ".csv" else "text"),
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                })

    reports.sort(key=lambda x: x["modified_at"], reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "active_tab": "reports",
            "reports": reports,
            "reports_dir": str(rep_dir),
        },
    )

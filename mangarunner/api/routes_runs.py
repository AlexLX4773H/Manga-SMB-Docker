import json
import os
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from mangarunner.db.database import get_db_session
from mangarunner.db.models import JobRun
from mangarunner.db import crud

router = APIRouter(prefix="/api/runs", tags=["Runs"])

class BatchDeleteRunsRequest(BaseModel):
    run_ids: List[str]

@router.get("")
def list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    category: Optional[str] = None,
    session: Session = Depends(get_db_session),
):
    runs = crud.get_runs(session, limit=limit, offset=offset, status=status, category=category)
    total = crud.count_runs(session, status=status)
    
    items = []
    for r in runs:
        reports = []
        if r.reports_json:
            try:
                reports = json.loads(r.reports_json)
            except Exception:
                pass
        items.append({
            "run_id": r.run_id,
            "script_id": r.script_id,
            "script_name": r.script_name,
            "category": r.category,
            "status": r.status,
            "dry_run": r.dry_run,
            "enqueued_at": r.enqueued_at.isoformat() if r.enqueued_at else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "duration_seconds": r.duration_seconds,
            "exit_code": r.exit_code,
            "reports": reports,
            "error_message": r.error_message,
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "runs": items,
    }

@router.get("/stats")
def get_run_stats(session: Session = Depends(get_db_session)):
    stats = crud.get_stats(session)
    last_run_dict = None
    if stats["last_run"]:
        lr = stats["last_run"]
        last_run_dict = {
            "run_id": lr.run_id,
            "script_name": lr.script_name,
            "status": lr.status,
            "enqueued_at": lr.enqueued_at.isoformat() if lr.enqueued_at else None,
        }
    stats["last_run"] = last_run_dict
    return stats

@router.get("/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_db_session)):
    run = crud.get_job_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    
    reports = []
    if run.reports_json:
        try:
            reports = json.loads(run.reports_json)
        except Exception:
            pass

    return {
        "run_id": run.run_id,
        "script_id": run.script_id,
        "script_name": run.script_name,
        "category": run.category,
        "script_path": run.script_path,
        "status": run.status,
        "dry_run": run.dry_run,
        "enqueued_at": run.enqueued_at.isoformat() if run.enqueued_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": run.duration_seconds,
        "exit_code": run.exit_code,
        "log_file": run.log_file,
        "reports": reports,
        "error_message": run.error_message,
    }

@router.get("/{run_id}/logs")
def get_run_logs(run_id: str, session: Session = Depends(get_db_session)):
    run = crud.get_job_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    
    log_content = ""
    if run.log_file and os.path.exists(run.log_file):
        try:
            with open(run.log_file, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
        except Exception as e:
            log_content = f"Error reading log file: {e}"
    else:
        log_content = "Log file not found."

    return Response(content=log_content, media_type="text/plain; charset=utf-8")

@router.post("/batch-delete")
def batch_delete_runs(req: BatchDeleteRunsRequest, session: Session = Depends(get_db_session)):
    if not req.run_ids:
        return {"status": "success", "deleted_count": 0}

    stmt = select(JobRun).where(
        and_(
            JobRun.run_id.in_(req.run_ids),
            JobRun.status.not_in(["running", "queued"])
        )
    )
    runs = list(session.execute(stmt).scalars().all())

    for r in runs:
        if r.log_file and os.path.exists(r.log_file):
            try:
                os.remove(r.log_file)
            except Exception:
                pass

    run_ids_to_del = [r.run_id for r in runs]
    deleted_count = crud.delete_job_runs(session, run_ids_to_del) if run_ids_to_del else 0
    return {"status": "success", "deleted_count": deleted_count}

@router.delete("/clear")
def clear_history_runs(
    status: Optional[str] = Query(None),
    session: Session = Depends(get_db_session)
):
    conditions = [JobRun.status.not_in(["running", "queued"])]
    if status and status in ("completed", "failed", "cancelled"):
        conditions.append(JobRun.status == status)

    stmt = select(JobRun).where(and_(*conditions))
    runs = list(session.execute(stmt).scalars().all())

    for r in runs:
        if r.log_file and os.path.exists(r.log_file):
            try:
                os.remove(r.log_file)
            except Exception:
                pass

    cleared_count = crud.clear_history_runs(session, status=status)
    return {"status": "success", "cleared_count": cleared_count}

@router.delete("/{run_id}")
def delete_run(run_id: str, session: Session = Depends(get_db_session)):
    run = crud.get_job_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status in ("running", "queued"):
        raise HTTPException(status_code=400, detail="Cannot delete an active or queued run.")
    
    if run.log_file and os.path.exists(run.log_file):
        try:
            os.remove(run.log_file)
        except Exception:
            pass

    crud.delete_job_run(session, run_id)
    return {"status": "success", "run_id": run_id}

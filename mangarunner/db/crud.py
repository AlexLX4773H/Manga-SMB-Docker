import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, desc, and_
from sqlalchemy.orm import Session
from mangarunner.db.models import JobRun

def create_job_run(
    session: Session,
    run_id: str,
    script_id: str,
    script_name: str,
    category: str,
    script_path: str,
    dry_run: bool = False,
    queue_position: int = 0,
) -> JobRun:
    job = JobRun(
        run_id=run_id,
        script_id=script_id,
        script_name=script_name,
        category=category,
        script_path=script_path,
        dry_run=dry_run,
        status="queued",
        queue_position=queue_position,
        enqueued_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job

def get_job_run(session: Session, run_id: str) -> Optional[JobRun]:
    stmt = select(JobRun).where(JobRun.run_id == run_id)
    result = session.execute(stmt)
    return result.scalar_one_or_none()

def get_active_job(session: Session) -> Optional[JobRun]:
    stmt = select(JobRun).where(JobRun.status == "running").order_by(JobRun.started_at.desc()).limit(1)
    result = session.execute(stmt)
    return result.scalar_one_or_none()

def get_queued_jobs(session: Session) -> List[JobRun]:
    stmt = select(JobRun).where(JobRun.status == "queued").order_by(JobRun.queue_position.asc(), JobRun.enqueued_at.asc())
    result = session.execute(stmt)
    return list(result.scalars().all())

def update_job_status(
    session: Session,
    run_id: str,
    status: str,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    duration_seconds: Optional[float] = None,
    exit_code: Optional[int] = None,
    log_file: Optional[str] = None,
    reports: Optional[List[str]] = None,
    error_message: Optional[str] = None,
) -> Optional[JobRun]:
    values: Dict[str, Any] = {"status": status}
    if started_at is not None:
        values["started_at"] = started_at
    if finished_at is not None:
        values["finished_at"] = finished_at
    if duration_seconds is not None:
        values["duration_seconds"] = duration_seconds
    if exit_code is not None:
        values["exit_code"] = exit_code
    if log_file is not None:
        values["log_file"] = log_file
    if reports is not None:
        values["reports_json"] = json.dumps(reports)
    if error_message is not None:
        values["error_message"] = error_message

    stmt = update(JobRun).where(JobRun.run_id == run_id).values(**values)
    session.execute(stmt)
    session.commit()
    return get_job_run(session, run_id)

def update_queue_positions(session: Session, position_map: Dict[str, int]) -> None:
    for run_id, pos in position_map.items():
        stmt = update(JobRun).where(JobRun.run_id == run_id).values(queue_position=pos)
        session.execute(stmt)
    session.commit()

def get_runs(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> List[JobRun]:
    stmt = select(JobRun)
    conditions = []
    if status:
        conditions.append(JobRun.status == status)
    if category:
        conditions.append(JobRun.category == category)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(JobRun.enqueued_at)).limit(limit).offset(offset)
    result = session.execute(stmt)
    return list(result.scalars().all())

def count_runs(session: Session, status: Optional[str] = None) -> int:
    stmt = select(func.count(JobRun.run_id))
    if status:
        stmt = stmt.where(JobRun.status == status)
    result = session.execute(stmt)
    return result.scalar_one() or 0

def delete_job_run(session: Session, run_id: str) -> bool:
    stmt = delete(JobRun).where(JobRun.run_id == run_id)
    result = session.execute(stmt)
    session.commit()
    return result.rowcount > 0

def clear_queued_runs(session: Session) -> int:
    stmt = delete(JobRun).where(JobRun.status == "queued")
    result = session.execute(stmt)
    session.commit()
    return result.rowcount

def get_stats(session: Session) -> Dict[str, Any]:
    total = count_runs(session)
    completed = count_runs(session, status="completed")
    failed = count_runs(session, status="failed")
    cancelled = count_runs(session, status="cancelled")
    running = count_runs(session, status="running")
    queued = count_runs(session, status="queued")

    last_run_stmt = select(JobRun).order_by(desc(JobRun.enqueued_at)).limit(1)
    last_res = session.execute(last_run_stmt)
    last_run = last_res.scalar_one_or_none()

    return {
        "total_runs": total,
        "completed_runs": completed,
        "failed_runs": failed,
        "cancelled_runs": cancelled,
        "running_runs": running,
        "queued_runs": queued,
        "last_run": last_run,
    }

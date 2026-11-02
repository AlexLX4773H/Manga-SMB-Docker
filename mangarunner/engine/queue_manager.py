import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from collections import deque

from mangarunner.config import load_config, AppConfig
from mangarunner.db.database import get_session_factory
from mangarunner.db import crud
from mangarunner.db.models import JobRun
from mangarunner.engine.script_registry import get_script_by_id
from shared.config import get_base_dir

class QueueManager:
    """Sequential FIFO runner coordinator and live SSE broadcaster."""

    _instance: Optional["QueueManager"] = None

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()
        self.active_run_id: Optional[str] = None
        self.active_job: Optional[Dict[str, Any]] = None
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._is_cancelled: bool = False
        
        self._listeners: Set[asyncio.Queue] = set()
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        
        # Circular buffer of recent log entries for active job (for late-connecting UI clients)
        self.recent_logs: deque = deque(maxlen=300)

    @property
    def shutdown_event(self) -> asyncio.Event:
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        return self._shutdown_event

    @classmethod
    def get_instance(cls) -> "QueueManager":
        if cls._instance is None:
            cls._instance = QueueManager()
        return cls._instance

    def subscribe(self) -> asyncio.Queue:
        """Subscribe an SSE client queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._listeners.discard(q)

    def broadcast(self, data: Dict[str, Any]) -> None:
        """Broadcasts event dictionary to all active SSE client queues."""
        dead_queues = []
        for q in self._listeners:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            self._listeners.discard(dq)

    def ensure_worker_running(self) -> None:
        """Starts the background worker queue consumer if not already running."""
        if self._worker_task is None or self._worker_task.done():
            self.shutdown_event.clear()
            self._worker_task = asyncio.create_task(self._queue_worker_loop())

    def start_worker(self) -> None:
        """Clean up orphaned runs and start worker if pending jobs exist."""
        session_factory = get_session_factory(self.config.database_path)
        with session_factory() as session:
            # Clean up stale running jobs from previous process restarts
            stale = crud.get_active_job(session)
            if stale and (self.active_run_id is None or stale.run_id != self.active_run_id):
                crud.update_job_status(
                    session=session,
                    run_id=stale.run_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                    error_message="Job interrupted by server restart.",
                )
            if crud.get_queued_jobs(session):
                self.ensure_worker_running()

    async def stop_worker(self) -> None:
        """Gracefully signals queue consumer to stop."""
        self.shutdown_event.set()
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _queue_worker_loop(self) -> None:
        """Worker loop consuming queued jobs 1-by-1 until queue is empty."""
        session_factory = get_session_factory(self.config.database_path)

        while not self.shutdown_event.is_set():
            try:
                next_job_id: Optional[str] = None
                with session_factory() as session:
                    queued_jobs = crud.get_queued_jobs(session)
                    if queued_jobs:
                        next_job_id = queued_jobs[0].run_id

                if next_job_id is None:
                    # Queue is empty, exit loop until next enqueue
                    break

                await self._run_single_job(next_job_id)
                # Small pause to allow process handles and SSE broadcasts to settle cleanly
                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[QueueManager] Error in worker loop: {e}", file=sys.stderr)
                await asyncio.sleep(2.0)

    async def _run_single_job(self, run_id: str) -> None:
        session_factory = get_session_factory(self.config.database_path)
        base_dir = get_base_dir()
        started_at = datetime.now(timezone.utc)

        with session_factory() as session:
            job = crud.get_job_run(session, run_id)
            if not job or job.status != "queued":
                return
            
            job = crud.update_job_status(
                session=session,
                run_id=run_id,
                status="running",
                started_at=started_at,
            )
            job_script_id = job.script_id
            job_script_name = job.script_name
            job_category = job.category
            job_script_path = job.script_path
            job_dry_run = job.dry_run

        self.active_run_id = run_id
        self._is_cancelled = False
        self.recent_logs.clear()

        self.active_job = {
            "run_id": run_id,
            "script_id": job_script_id,
            "script_name": job_script_name,
            "category": job_category,
            "dry_run": job_dry_run,
            "status": "running",
            "started_at": started_at.isoformat(),
        }

        self.broadcast({
            "type": "job_started",
            "run_id": run_id,
            "job": self.active_job,
            "timestamp": started_at.isoformat(),
        })
        self.broadcast({
            "type": "queue_updated",
            "action": "started",
            "run_id": run_id,
        })

        log_file_path = Path(self.config.logs_dir) / f"{run_id}.log"
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_file_path, "w", encoding="utf-8", errors="replace")

        script_abs_path = str(base_dir / job_script_path)
        cmd = [
            sys.executable,
            "-u",
            script_abs_path,
            "--dry-run" if job_dry_run else "--live",
            "--yes",
        ]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["DRY_RUN"] = "1" if job_dry_run else "0"
        env["AUTO_CONFIRM"] = "1"
        env["MANGA_ROOT"] = self.config.manga_root
        env["REPORTS_DIR"] = self.config.reports_dir
        env["DATA_DIR"] = self.config.data_dir

        header_line = f"=== [Job {run_id[:8]}] Starting '{job_script_name}' (Dry Run: {job_dry_run}) at {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')} ===\n"
        log_file.write(header_line)
        log_file.flush()
        self._emit_log_line(run_id, header_line.strip())

        exit_code = -1
        error_msg = None

        try:
            self._current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(base_dir),
                env=env,
            )

            while True:
                line_bytes = await self._current_process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                log_file.write(line + "\n")
                log_file.flush()
                self._emit_log_line(run_id, line)

            exit_code = await self._current_process.wait()

        except asyncio.CancelledError:
            self._is_cancelled = True
            error_msg = "Job cancelled by system shutdown."
        except Exception as e:
            error_msg = str(e)
            err_line = f"[QueueManager Error] {error_msg}"
            log_file.write(err_line + "\n")
            log_file.flush()
            self._emit_log_line(run_id, err_line)
        finally:
            finished_at = datetime.now(timezone.utc)
            duration = (finished_at - started_at).total_seconds()
            
            status = "completed"
            if self._is_cancelled:
                status = "cancelled"
            elif exit_code != 0:
                status = "failed"

            trailer_line = f"\n=== [Job {run_id[:8]}] Finished with status: {status.upper()} (Exit Code: {exit_code}) in {duration:.2f}s ==="
            log_file.write(trailer_line + "\n")
            log_file.close()
            self._emit_log_line(run_id, trailer_line.strip())

            detected_reports = self._detect_generated_reports(started_at)

            with session_factory() as session:
                crud.update_job_status(
                    session=session,
                    run_id=run_id,
                    status=status,
                    finished_at=finished_at,
                    duration_seconds=duration,
                    exit_code=exit_code,
                    log_file=str(log_file_path),
                    reports=detected_reports,
                    error_message=error_msg,
                )

            finished_event = {
                "type": "job_finished",
                "run_id": run_id,
                "status": status,
                "exit_code": exit_code,
                "duration_seconds": duration,
                "reports": detected_reports,
                "timestamp": finished_at.isoformat(),
            }
            self.broadcast(finished_event)

            self.active_run_id = None
            self.active_job = None
            self._current_process = None
            self._is_cancelled = False

            self.broadcast({
                "type": "queue_updated",
                "action": "finished",
                "run_id": run_id,
            })

    def _emit_log_line(self, run_id: str, line: str) -> None:
        log_item = {
            "type": "log",
            "run_id": run_id,
            "line": line,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.recent_logs.append(log_item)
        self.broadcast(log_item)

    def _detect_generated_reports(self, since_time: datetime) -> List[str]:
        rep_dir = Path(self.config.reports_dir)
        if not rep_dir.exists():
            return []
        
        reports_found = []
        since_ts = since_time.timestamp() - 2.0
        
        for p in rep_dir.iterdir():
            if p.is_file() and p.suffix.lower() in (".xlsx", ".txt", ".csv", ".json", ".log"):
                try:
                    if p.stat().st_mtime >= since_ts:
                        reports_found.append(p.name)
                except Exception:
                    pass
        return sorted(reports_found)

    async def enqueue_job(self, script_id: str, dry_run: bool = False) -> JobRun:
        script = get_script_by_id(script_id)
        if not script:
            raise ValueError(f"Script with id '{script_id}' not found.")

        run_id = str(uuid.uuid4())
        session_factory = get_session_factory(self.config.database_path)

        with session_factory() as session:
            queued = crud.get_queued_jobs(session)
            max_pos = max([j.queue_position for j in queued if j.queue_position is not None] or [0])
            position = max_pos + 1

            job = crud.create_job_run(
                session=session,
                run_id=run_id,
                script_id=script.id,
                script_name=script.name,
                category=script.category,
                script_path=script.file_path,
                dry_run=dry_run,
                queue_position=position,
            )

        self.broadcast({
            "type": "queue_updated",
            "action": "enqueued",
            "run_id": run_id,
            "script_name": script.name,
            "dry_run": dry_run,
        })
        self.ensure_worker_running()
        return job

    async def enqueue_batch(self, script_ids: List[str], dry_run: bool = False) -> List[JobRun]:
        session_factory = get_session_factory(self.config.database_path)
        enqueued_jobs: List[JobRun] = []

        with session_factory() as session:
            queued = crud.get_queued_jobs(session)
            max_pos = max([j.queue_position for j in queued if j.queue_position is not None] or [0])

            for sid in script_ids:
                script = get_script_by_id(sid)
                if not script:
                    continue
                max_pos += 1
                run_id = str(uuid.uuid4())
                job = crud.create_job_run(
                    session=session,
                    run_id=run_id,
                    script_id=script.id,
                    script_name=script.name,
                    category=script.category,
                    script_path=script.file_path,
                    dry_run=dry_run,
                    queue_position=max_pos,
                )
                enqueued_jobs.append(job)

        if enqueued_jobs:
            self.broadcast({
                "type": "queue_updated",
                "action": "batch_enqueued",
                "count": len(enqueued_jobs),
            })
            self.ensure_worker_running()

        return enqueued_jobs

    async def cancel_active_job(self) -> bool:
        if not self.active_run_id or not self._current_process:
            return False

        self._is_cancelled = True
        try:
            self._current_process.terminate()
            self._emit_log_line(self.active_run_id, "[SYSTEM] Termination signal sent to process...")
            return True
        except Exception as e:
            print(f"[QueueManager] Failed to terminate active job: {e}")
            return False

    async def remove_from_queue(self, run_id: str) -> bool:
        session_factory = get_session_factory(self.config.database_path)
        with session_factory() as session:
            job = crud.get_job_run(session, run_id)
            if not job or job.status != "queued":
                return False
            success = crud.delete_job_run(session, run_id)
            if success:
                remaining = crud.get_queued_jobs(session)
                pos_map = {j.run_id: i + 1 for i, j in enumerate(remaining)}
                crud.update_queue_positions(session, pos_map)
            
        if success:
            self.broadcast({
                "type": "queue_updated",
                "action": "removed",
                "run_id": run_id,
            })
        return success

    async def reorder_queue(self, run_id: str, direction: str) -> bool:
        session_factory = get_session_factory(self.config.database_path)
        with session_factory() as session:
            queued = crud.get_queued_jobs(session)
            ids = [j.run_id for j in queued]
            if run_id not in ids:
                return False

            idx = ids.index(run_id)
            if direction == "up" and idx > 0:
                ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
            elif direction == "down" and idx < len(ids) - 1:
                ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
            else:
                return False

            pos_map = {jid: i + 1 for i, jid in enumerate(ids)}
            crud.update_queue_positions(session, pos_map)

        self.broadcast({"type": "queue_updated", "action": "reordered"})
        return True

    async def clear_queue(self) -> int:
        session_factory = get_session_factory(self.config.database_path)
        with session_factory() as session:
            count = crud.clear_queued_runs(session)
            
        self.broadcast({"type": "queue_updated", "action": "cleared", "count": count})
        return count

    async def get_queue_status(self) -> Dict[str, Any]:
        session_factory = get_session_factory(self.config.database_path)
        with session_factory() as session:
            active = crud.get_active_job(session)
            queued = crud.get_queued_jobs(session)

            active_dict = None
            if active and self.active_run_id == active.run_id:
                active_dict = {
                    "run_id": active.run_id,
                    "script_id": active.script_id,
                    "script_name": active.script_name,
                    "category": active.category,
                    "dry_run": active.dry_run,
                    "started_at": active.started_at.isoformat() if active.started_at else None,
                }
            elif self.active_job:
                active_dict = self.active_job

            queued_list = [
                {
                    "run_id": q.run_id,
                    "script_id": q.script_id,
                    "script_name": q.script_name,
                    "category": q.category,
                    "dry_run": q.dry_run,
                    "position": q.queue_position,
                    "enqueued_at": q.enqueued_at.isoformat() if q.enqueued_at else None,
                } for q in queued
            ]

        return {
            "is_running": self.active_run_id is not None,
            "active_run": active_dict,
            "queued_runs": queued_list,
            "queue_count": len(queued_list),
        }

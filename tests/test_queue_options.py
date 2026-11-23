import sys
import os
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mangarunner.db.database import get_session_factory, init_db
from mangarunner.db import crud
from mangarunner.engine.queue_manager import QueueManager
from mangarunner.config import load_config
from mangarunner.api.routes_queue import enqueue_job, enqueue_batch, EnqueueRequest, EnqueueBatchRequest
from fastapi import HTTPException

async def async_test_queue_options():
    print("Testing Queue Options & Parallel Execution Prevention...")
    test_db = Path("data/test_queue_opts.db")
    if test_db.exists():
        test_db.unlink()
        
    init_db(str(test_db))
    cfg = load_config()
    cfg.database_path = str(test_db)
    
    qm = QueueManager.get_instance()
    qm.config = cfg
    qm.active_run_id = None
    qm.active_job = None
    # Prevent background process spawning during unit tests
    qm.ensure_worker_running = lambda: None

    session_factory = get_session_factory(str(test_db))

    # --- Test 1: When idle, enqueue with queue_if_running=True or False succeeds ---
    res1 = await enqueue_job(EnqueueRequest(script_id="copy_manga_folder", dry_run=True, queue_if_running=False))
    assert res1["status"] == "success"
    assert res1["script_name"] == "Sync Mihon Folders to Categorized"
    assert res1["position"] == 1
    assert res1["active_job_running"] is False
    assert res1["will_wait_in_queue"] is False
    print("[OK] Test 1: Enqueue when idle succeeds regardless of queue_if_running flag.")

    # Clean up test 1 job
    with session_factory() as session:
        crud.delete_job_run(session, res1["run_id"])

    # --- Test 2: Simulate an actively running job ---
    simulated_run_id = str(uuid.uuid4())
    qm.active_run_id = simulated_run_id
    qm.active_job = {
        "run_id": simulated_run_id,
        "script_id": "check_new_manga",
        "script_name": "Check New Manga from Source",
        "category": "Check Manga",
        "dry_run": False,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    with session_factory() as session:
        crud.create_job_run(
            session=session,
            run_id=simulated_run_id,
            script_id="check_new_manga",
            script_name="Check New Manga from Source",
            category="Check Manga",
            script_path="Check Manga/Check_new_Manga_from_source.py",
            dry_run=False,
            queue_position=None,
        )
        crud.update_job_status(session, simulated_run_id, status="running", started_at=datetime.now(timezone.utc))

    print("[OK] Simulated active job running.")

    # --- Test 3: When active job is running, enqueue with queue_if_running=False must be blocked with 409 Conflict ---
    try:
        await enqueue_job(EnqueueRequest(script_id="copy_manga_folder", dry_run=False, queue_if_running=False))
        assert False, "Should have raised HTTPException 409 Conflict"
    except HTTPException as e:
        assert e.status_code == 409
        assert "parallel execution is strictly disabled" in e.detail or "currently running" in e.detail
        print(f"[OK] Test 3: Blocked parallel execution attempt with 409 Conflict: {e.detail}")

    # --- Test 4: When active job is running, enqueue with queue_if_running=True must succeed and queue sequentially ---
    res_queued = await enqueue_job(EnqueueRequest(script_id="copy_manga_folder", dry_run=False, queue_if_running=True))
    assert res_queued["status"] == "success"
    assert res_queued["active_job_running"] is True
    assert res_queued["will_wait_in_queue"] is True
    assert res_queued["position"] == 1
    assert "will execute sequentially after active job" in res_queued["message"]
    print(f"[OK] Test 4: Successfully enqueued job sequentially while active job runs: {res_queued['message']}")

    # --- Test 5: Second queued job gets position 2 ---
    res_queued2 = await enqueue_job(EnqueueRequest(script_id="copy_manhwa_cbz", dry_run=True, queue_if_running=True))
    assert res_queued2["status"] == "success"
    assert res_queued2["position"] == 2
    print(f"[OK] Test 5: Next job enqueued at position #{res_queued2['position']} strictly in FIFO sequence.")

    # --- Test 6: Batch enqueue with queue_if_running=False while busy must fail with 409 Conflict ---
    try:
        await enqueue_batch(EnqueueBatchRequest(script_ids=["convert_to_cbz"], dry_run=True, queue_if_running=False))
        assert False, "Batch should have raised 409 Conflict when queue_if_running=False and busy"
    except HTTPException as e:
        assert e.status_code == 409
        print(f"[OK] Test 6: Blocked batch parallel execution attempt with 409 Conflict: {e.detail}")

    # --- Test 7: Batch enqueue with queue_if_running=True while busy succeeds ---
    res_batch = await enqueue_batch(EnqueueBatchRequest(script_ids=["convert_to_cbz", "mirror_manga_to_cbz"], dry_run=True, queue_if_running=True))
    assert res_batch["status"] == "success"
    assert res_batch["enqueued_count"] == 2
    assert res_batch["active_job_running"] is True
    print(f"[OK] Test 7: Successfully batch-enqueued sequentially while busy.")

    # Clean up
    qm.active_run_id = None
    qm.active_job = None
    try:
        from mangarunner.db.database import get_engine
        get_engine(str(test_db)).dispose()
        if test_db.exists():
            test_db.unlink()
    except Exception:
        pass

    print("\n>>> ALL QUEUE OPTION TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    asyncio.run(async_test_queue_options())

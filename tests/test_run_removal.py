import sys
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mangarunner.db.database import get_session_factory, init_db
from mangarunner.db import crud
from mangarunner.db.models import JobRun
from mangarunner.api.routes_runs import delete_run, batch_delete_runs, clear_history_runs, BatchDeleteRunsRequest
from fastapi import HTTPException
from fastapi.templating import Jinja2Templates

def run_tests():
    print("Testing Run History Removal Functionality...")
    test_db = Path("data/test_runs.db")
    if test_db.exists():
        test_db.unlink()
        
    init_db(str(test_db))
    session_factory = get_session_factory(str(test_db))

    with session_factory() as session:
        # Create dummy runs: 2 completed, 1 failed, 1 cancelled, 1 queued, 1 running
        r1 = crud.create_job_run(session, run_id=str(uuid.uuid4()), script_id="s1", script_name="Script 1", category="Cat A", script_path="path1")
        crud.update_job_status(session, r1.run_id, status="completed", finished_at=datetime.now(timezone.utc))

        r2 = crud.create_job_run(session, run_id=str(uuid.uuid4()), script_id="s2", script_name="Script 2", category="Cat A", script_path="path2")
        crud.update_job_status(session, r2.run_id, status="completed", finished_at=datetime.now(timezone.utc))

        r3 = crud.create_job_run(session, run_id=str(uuid.uuid4()), script_id="s3", script_name="Script 3", category="Cat B", script_path="path3")
        crud.update_job_status(session, r3.run_id, status="failed", finished_at=datetime.now(timezone.utc))

        r4 = crud.create_job_run(session, run_id=str(uuid.uuid4()), script_id="s4", script_name="Script 4", category="Cat B", script_path="path4")
        crud.update_job_status(session, r4.run_id, status="cancelled", finished_at=datetime.now(timezone.utc))

        r_queued = crud.create_job_run(session, run_id=str(uuid.uuid4()), script_id="s_q", script_name="Queued Script", category="Cat C", script_path="path_q")
        
        r_running = crud.create_job_run(session, run_id=str(uuid.uuid4()), script_id="s_r", script_name="Running Script", category="Cat C", script_path="path_r")
        crud.update_job_status(session, r_running.run_id, status="running", started_at=datetime.now(timezone.utc))

        # Create dummy log file for r1
        log_dir = Path("data/test_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        dummy_log = log_dir / f"{r1.run_id}.log"
        dummy_log.write_text("Test log content", encoding="utf-8")
        crud.update_job_status(session, r1.run_id, status="completed", log_file=str(dummy_log))

        print("[OK] Created test runs in database.")

        # Test 1: Single run deletion via delete_run
        del_res = delete_run(r1.run_id, session=session)
        assert del_res["status"] == "success"
        assert crud.get_job_run(session, r1.run_id) is None
        assert not dummy_log.exists(), "Log file should be removed upon deletion"
        print("[OK] Test 1: Single run deletion & log file cleanup passed.")

        # Test 2: Cannot delete queued or running runs
        try:
            delete_run(r_queued.run_id, session=session)
            assert False, "Should have raised HTTPException for queued run"
        except HTTPException as e:
            assert e.status_code == 400
            print("[OK] Test 2a: Blocked deleting queued run.")

        try:
            delete_run(r_running.run_id, session=session)
            assert False, "Should have raised HTTPException for running run"
        except HTTPException as e:
            assert e.status_code == 400
            print("[OK] Test 2b: Blocked deleting running run.")

        # Test 3: Batch delete
        # Create log for r3
        dummy_log3 = log_dir / f"{r3.run_id}.log"
        dummy_log3.write_text("Log 3", encoding="utf-8")
        crud.update_job_status(session, r3.run_id, status="failed", log_file=str(dummy_log3))

        batch_res = batch_delete_runs(BatchDeleteRunsRequest(run_ids=[r2.run_id, r3.run_id, r_running.run_id]), session=session)
        # r_running should be skipped because it is running!
        assert batch_res["status"] == "success"
        assert batch_res["deleted_count"] == 2
        assert crud.get_job_run(session, r2.run_id) is None
        assert crud.get_job_run(session, r3.run_id) is None
        assert not dummy_log3.exists()
        assert crud.get_job_run(session, r_running.run_id) is not None
        print("[OK] Test 3: Batch deletion of runs (safely skipping active) passed.")

        # Test 4: Clear history with status filter
        # Add another cancelled run
        r5 = crud.create_job_run(session, run_id=str(uuid.uuid4()), script_id="s5", script_name="Script 5", category="Cat A", script_path="path5")
        crud.update_job_status(session, r5.run_id, status="cancelled")

        clear_res = clear_history_runs(status="cancelled", session=session)
        assert clear_res["status"] == "success"
        assert clear_res["cleared_count"] == 2 # r4 and r5
        assert crud.get_job_run(session, r4.run_id) is None
        assert crud.get_job_run(session, r5.run_id) is None
        assert crud.get_job_run(session, r_running.run_id) is not None
        assert crud.get_job_run(session, r_queued.run_id) is not None
        print("[OK] Test 4: Clear history by status passed.")

        # Test 6: Verify template rendering with runs
        from mangarunner.web.routes import templates
        from starlette.requests import Request
        scope = {"type": "http", "method": "GET", "path": "/runs", "headers": []}
        req = Request(scope)
        rendered_runs = templates.TemplateResponse(
            request=req,
            name="runs.html",
            context={
                "active_tab": "runs",
                "runs": [
                    {
                        "run_id": "test-uuid-1234",
                        "script_name": "Test Script",
                        "category": "Test Cat",
                        "status": "completed",
                        "dry_run": False,
                        "enqueued_at": datetime.now(timezone.utc),
                        "started_at": datetime.now(timezone.utc),
                        "finished_at": datetime.now(timezone.utc),
                        "duration_seconds": 12.3,
                        "exit_code": 0,
                        "reports": ["test.xlsx"],
                        "error_message": None,
                    }
                ],
                "total_count": 1,
                "current_page": 1,
                "total_pages": 1,
                "filter_status": "",
                "filter_category": "",
            }
        )
        assert rendered_runs.status_code == 200
        assert "Delete Selected" in rendered_runs.body.decode("utf-8")
        assert "deleteRunRecord" in rendered_runs.body.decode("utf-8")
        print("[OK] Test 6: Template runs.html rendered successfully.")

        # Test 7: Verify run_detail.html template rendering
        class DummyRun:
            run_id = "test-uuid-1234"
            script_id = "s1"
            script_name = "Test Script"
            category = "Test Cat"
            script_path = "Check Manga/test.py"
            status = "completed"
            dry_run = False
            exit_code = 0
            enqueued_at = datetime.now(timezone.utc)
            started_at = datetime.now(timezone.utc)
            finished_at = datetime.now(timezone.utc)
            duration_seconds = 12.3
            error_message = None

        rendered_detail = templates.TemplateResponse(
            request=req,
            name="run_detail.html",
            context={
                "active_tab": "runs",
                "run": DummyRun(),
                "reports": ["test.xlsx"],
                "log_content": "Sample logs...",
            }
        )
        assert rendered_detail.status_code == 200
        assert "Delete Run" in rendered_detail.body.decode("utf-8")
        print("[OK] Test 7: Template run_detail.html rendered successfully.")

    # Clean up test artifacts
    from mangarunner.db.database import get_engine
    get_engine(str(test_db)).dispose()
    if test_db.exists():
        try:
            test_db.unlink()
        except Exception:
            pass
    import shutil
    if log_dir.exists():
        shutil.rmtree(log_dir)

    print("\n>>> ALL RUN REMOVAL TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    run_tests()

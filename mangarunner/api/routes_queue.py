from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mangarunner.engine.queue_manager import QueueManager

router = APIRouter(prefix="/api/queue", tags=["Queue"])

class EnqueueRequest(BaseModel):
    script_id: str
    dry_run: bool = False

class EnqueueBatchRequest(BaseModel):
    script_ids: List[str]
    dry_run: bool = False

class ReorderRequest(BaseModel):
    direction: str  # "up" or "down"

@router.get("/status")
async def get_queue_status():
    qm = QueueManager.get_instance()
    return await qm.get_queue_status()

@router.post("/enqueue")
async def enqueue_job(req: EnqueueRequest):
    qm = QueueManager.get_instance()
    try:
        job = await qm.enqueue_job(req.script_id, dry_run=req.dry_run)
        return {
            "status": "success",
            "run_id": job.run_id,
            "script_name": job.script_name,
            "dry_run": job.dry_run,
            "position": job.queue_position,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue job: {e}")

@router.post("/enqueue-batch")
async def enqueue_batch(req: EnqueueBatchRequest):
    qm = QueueManager.get_instance()
    jobs = await qm.enqueue_batch(req.script_ids, dry_run=req.dry_run)
    return {
        "status": "success",
        "enqueued_count": len(jobs),
        "run_ids": [j.run_id for j in jobs],
    }

@router.post("/cancel-active")
async def cancel_active():
    qm = QueueManager.get_instance()
    success = await qm.cancel_active_job()
    if not success:
        return {"status": "error", "message": "No active job running to cancel."}
    return {"status": "success", "message": "Cancellation signal sent."}

@router.delete("/remove/{run_id}")
async def remove_queued(run_id: str):
    qm = QueueManager.get_instance()
    success = await qm.remove_from_queue(run_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or not in queued status.")
    return {"status": "success", "run_id": run_id}

@router.post("/reorder/{run_id}")
async def reorder_queued(run_id: str, req: ReorderRequest):
    qm = QueueManager.get_instance()
    success = await qm.reorder_queue(run_id, req.direction)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot move job in that direction.")
    return {"status": "success"}

@router.delete("/clear")
async def clear_queue():
    qm = QueueManager.get_instance()
    cleared = await qm.clear_queue()
    return {"status": "success", "cleared_count": cleared}


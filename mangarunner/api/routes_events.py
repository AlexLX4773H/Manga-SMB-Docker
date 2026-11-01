import json
import asyncio
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from mangarunner.engine.queue_manager import QueueManager

router = APIRouter(prefix="/api/events", tags=["Live Events"])

@router.get("")
async def sse_events(request: Request):
    """Server-Sent Events stream for live queue status and real-time process logs."""
    qm = QueueManager.get_instance()
    queue = qm.subscribe()

    async def event_generator():
        try:
            # Yield initial status immediately
            status_data = await qm.get_queue_status()
            yield {
                "event": "status",
                "data": json.dumps(status_data),
            }

            # If there's an active job, send any recent log lines from memory buffer
            if qm.active_run_id and qm.recent_logs:
                for log_item in list(qm.recent_logs):
                    yield {
                        "event": "log",
                        "data": json.dumps(log_item),
                    }

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    evt_type = event_data.get("type", "message")
                    yield {
                        "event": evt_type,
                        "data": json.dumps(event_data),
                    }
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield {
                        "event": "ping",
                        "data": "{}",
                    }

        except asyncio.CancelledError:
            pass
        finally:
            qm.unsubscribe(queue)

    return EventSourceResponse(event_generator())


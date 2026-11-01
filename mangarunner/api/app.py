from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mangarunner.config import load_config
from mangarunner.db.database import init_db
from mangarunner.engine.queue_manager import QueueManager
from mangarunner.api.routes_queue import router as queue_router
from mangarunner.api.routes_scripts import router as scripts_router
from mangarunner.api.routes_runs import router as runs_router
from mangarunner.api.routes_reports import router as reports_router
from mangarunner.api.routes_events import router as events_router
from mangarunner.web.routes import router as web_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager initializing database and background queue runner."""
    config = load_config()
    init_db(config.database_path)
    
    # Initialize and start queue manager
    qm = QueueManager.get_instance()
    qm.config = config
    qm.start_worker()
    print(f"Manga SMB Suite started on port {config.server.port}. Linux Root: {config.manga_root}")
    
    yield
    
    print("Manga SMB Suite shutting down...")
    await qm.stop_worker()

def create_app() -> FastAPI:
    app = FastAPI(
        title="Manga SMB Suite",
        description="Automated Manga SMB Docker Dashboard, Sequential Queue & Report Viewer",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static assets
    static_dir = Path(__file__).parent.parent / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # API Routers
    app.include_router(queue_router)
    app.include_router(scripts_router)
    app.include_router(runs_router)
    app.include_router(reports_router)
    app.include_router(events_router)

    # Web UI Router
    app.include_router(web_router)

    @app.get("/api/health", tags=["Health"])
    def health_check():
        return {
            "status": "ok",
            "app": "Manga SMB Suite",
            "version": "1.0.0",
        }

    return app

app = create_app()

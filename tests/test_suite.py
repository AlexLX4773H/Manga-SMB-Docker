import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mangarunner.api.app import app
from mangarunner.engine.script_registry import get_registered_scripts
from mangarunner.config import load_config
from mangarunner.db.database import init_db

def test_full_system():
    print("Testing Manga SMB Suite...")
    cfg = load_config()
    init_db(cfg.database_path)

    # 1. Test script registry
    scripts = get_registered_scripts()
    print(f"[OK] Found {len(scripts)} scripts registered.")
    assert len(scripts) >= 14

    # 2. TestClient
    with TestClient(app) as client:
        # Health check
        res = client.get("/api/health")
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok"
        print("[OK] /api/health returned 200 OK.")

        # HTML Pages
        for endpoint in ["/", "/scripts", "/active", "/runs", "/reports"]:
            res = client.get(endpoint)
            assert res.status_code == 200, f"Endpoint {endpoint} failed: {res.status_code}"
            assert "<!DOCTYPE html>" in res.text
            print(f"[OK] {endpoint} rendered HTML with 200 OK.")

        # Scripts API
        res = client.get("/api/scripts")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 14
        print("[OK] /api/scripts returned valid catalog.")

        # Queue Status API
        res = client.get("/api/queue/status")
        assert res.status_code == 200
        print("[OK] /api/queue/status returned 200 OK.")

        # Reports API
        res = client.get("/api/reports")
        assert res.status_code == 200
        print("[OK] /api/reports returned 200 OK.")

        # Run Stats API
        res = client.get("/api/runs/stats")
        assert res.status_code == 200
        print("[OK] /api/runs/stats returned 200 OK.")

    print("\n>>> ALL TEST CHECKS PASSED WITH 100% SUCCESS! <<<")

if __name__ == "__main__":
    test_full_system()

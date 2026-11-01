import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml

from shared.config import get_manga_root, get_reports_dir, get_data_dir

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 7070

class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    manga_root: str = Field(default_factory=get_manga_root)
    data_dir: str = Field(default_factory=lambda: str(get_data_dir()))
    reports_dir: str = Field(default_factory=lambda: str(get_reports_dir()))
    database_path: str = Field(default_factory=lambda: str(get_data_dir() / "mangarunner.db"))
    logs_dir: str = Field(default_factory=lambda: str(get_data_dir() / "logs"))

def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Loads configuration from YAML if exists, with environment variable overrides."""
    config_file = config_path or os.environ.get("MANGARUNNER_CONFIG", "config.yaml")
    cfg_data = {}
    
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not read {config_file}: {e}")

    # Environment variable overrides
    server_port = int(os.environ.get("PORT", cfg_data.get("server", {}).get("port", 7070)))
    server_host = os.environ.get("HOST", cfg_data.get("server", {}).get("host", "0.0.0.0"))
    manga_root = os.environ.get("MANGA_ROOT", cfg_data.get("manga_root", get_manga_root()))
    reports_dir = os.environ.get("REPORTS_DIR", cfg_data.get("reports_dir", str(get_reports_dir())))
    data_dir = os.environ.get("DATA_DIR", cfg_data.get("data_dir", str(get_data_dir())))
    db_path = os.environ.get("DATABASE_PATH", cfg_data.get("database_path", str(Path(data_dir) / "mangarunner.db")))
    logs_dir = os.environ.get("LOGS_DIR", cfg_data.get("logs_dir", str(Path(data_dir) / "logs")))

    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    Path(logs_dir).mkdir(parents=True, exist_ok=True)

    return AppConfig(
        server=ServerConfig(host=server_host, port=server_port),
        manga_root=manga_root,
        data_dir=data_dir,
        reports_dir=reports_dir,
        database_path=db_path,
        logs_dir=logs_dir,
    )


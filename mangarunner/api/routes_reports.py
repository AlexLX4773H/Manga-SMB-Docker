import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
import pandas as pd

from mangarunner.config import load_config
from shared.config import get_reports_dir

router = APIRouter(prefix="/api/reports", tags=["Reports"])

def _get_reports_directory() -> Path:
    cfg = load_config()
    p = Path(cfg.reports_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p

@router.get("")
async def list_reports():
    reports_dir = _get_reports_directory()
    valid_extensions = {".xlsx", ".xls", ".txt", ".csv", ".log"}
    
    files = []
    if reports_dir.exists():
        for item in reports_dir.iterdir():
            if item.is_file() and item.suffix.lower() in valid_extensions:
                stat = item.stat()
                ext = item.suffix.lower()
                ftype = "excel" if ext in (".xlsx", ".xls") else ("csv" if ext == ".csv" else "text")
                files.append({
                    "filename": item.name,
                    "extension": ext,
                    "file_type": ftype,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })

    # Sort newest first
    files.sort(key=lambda x: x["modified_at"], reverse=True)
    return {
        "total": len(files),
        "reports": files,
        "directory": str(reports_dir),
    }

@router.get("/{filename}/download")
async def download_report(filename: str):
    reports_dir = _get_reports_directory()
    # Path traversal protection
    clean_filename = os.path.basename(filename)
    target_path = reports_dir / clean_filename

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found.")

    media_type = "application/octet-stream"
    if clean_filename.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif clean_filename.endswith(".txt"):
        media_type = "text/plain; charset=utf-8"
    elif clean_filename.endswith(".csv"):
        media_type = "text/csv; charset=utf-8"

    return FileResponse(
        path=str(target_path),
        filename=clean_filename,
        media_type=media_type,
    )

@router.get("/{filename}/preview")
async def preview_report(filename: str, max_rows: int = Query(100, ge=10, le=500)):
    reports_dir = _get_reports_directory()
    clean_filename = os.path.basename(filename)
    target_path = reports_dir / clean_filename

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found.")

    ext = target_path.suffix.lower()

    if ext in (".txt", ".log"):
        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(500)]
                content = "".join(lines)
            return {
                "filename": clean_filename,
                "type": "text",
                "content": content,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read text report: {e}")

    elif ext in (".xlsx", ".xls"):
        try:
            # Inspect sheets
            xl = pd.ExcelFile(str(target_path))
            sheets_data = []
            for sheet_name in xl.sheet_names:
                df = xl.parse(sheet_name, nrows=max_rows)
                # Fill NaN with empty string
                df = df.fillna("")
                columns = [str(c) for c in df.columns]
                # Convert rows to list of lists (string representation)
                rows = []
                for _, row in df.iterrows():
                    rows.append([str(v) for v in row.values])
                
                sheets_data.append({
                    "sheet_name": sheet_name,
                    "columns": columns,
                    "rows": rows,
                    "total_preview_rows": len(rows),
                })

            return {
                "filename": clean_filename,
                "type": "excel",
                "sheets": sheets_data,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse Excel report: {e}")

    elif ext == ".csv":
        try:
            df = pd.read_csv(str(target_path), nrows=max_rows).fillna("")
            columns = [str(c) for c in df.columns]
            rows = [[str(v) for v in row.values] for _, row in df.iterrows()]
            return {
                "filename": clean_filename,
                "type": "csv",
                "columns": columns,
                "rows": rows,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse CSV report: {e}")

    else:
        raise HTTPException(status_code=400, detail=f"Preview not supported for file extension {ext}")

@router.delete("/{filename}")
async def delete_report(filename: str):
    reports_dir = _get_reports_directory()
    clean_filename = os.path.basename(filename)
    target_path = reports_dir / clean_filename

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found.")

    try:
        target_path.unlink()
        return {"status": "success", "filename": clean_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {e}")


from fastapi import APIRouter, HTTPException
from mangarunner.engine.script_registry import get_registered_scripts, get_script_by_id, get_scripts_by_category

router = APIRouter(prefix="/api/scripts", tags=["Scripts"])

@router.get("")
async def list_scripts():
    scripts = get_registered_scripts()
    by_cat = get_scripts_by_category()
    return {
        "total": len(scripts),
        "scripts": list(scripts.values()),
        "categories": by_cat,
    }

@router.get("/{script_id}")
async def get_script(script_id: str):
    script = get_script_by_id(script_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' not found.")
    return script


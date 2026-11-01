import os
import sys
from pathlib import Path
from typing import List, Union

# Defaults
WINDOWS_DEFAULT_ROOT = r"Z:"
LINUX_DEFAULT_ROOT = "/sg2b/Share2sgb"

def get_manga_root() -> str:
    """
    Returns the target root path.
    Prioritizes environment variable MANGA_ROOT.
    Otherwise on Linux/Docker returns /sg2b/Share2sgb, on Windows returns Z:.
    """
    if "MANGA_ROOT" in os.environ and os.environ["MANGA_ROOT"].strip():
        return os.environ["MANGA_ROOT"].strip().rstrip("/\\")
    
    if os.name != "nt":
        return LINUX_DEFAULT_ROOT
    return WINDOWS_DEFAULT_ROOT

def resolve_path(win_path: Union[str, Path]) -> str:
    r"""
    Translates Windows Z:\ paths to Linux /sg2b/Share2sgb/ paths (or vice-versa).
    Preserves existing paths if they do not start with Z: or if already target formatted.
    """
    if not win_path:
        return ""
    
    p_str = str(win_path).strip()
    root = get_manga_root()
    
    # Check if path starts with Z:\ or Z:/ (case-insensitive)
    if p_str.upper().startswith("Z:\\") or p_str.upper().startswith("Z:/"):
        # Strip drive letter and slash
        relative_part = p_str[3:]
        # Normalize slashes
        if os.name != "nt" or root.startswith("/"):
            # Linux target
            clean_rel = relative_part.replace("\\", "/").lstrip("/")
            return f"{root}/{clean_rel}"
        else:
            # Windows target
            clean_rel = relative_part.replace("/", "\\").lstrip("\\")
            return f"{root}\\{clean_rel}"
    elif p_str.upper() == "Z:" or p_str.upper() == "Z:\\" or p_str.upper() == "Z:/":
        return root

    # If it's already an absolute Linux path or relative path, normalize for the active OS
    if os.name != "nt":
        return p_str.replace("\\", "/")
    return p_str

def resolve_paths(paths: List[Union[str, Path]]) -> List[str]:
    """Helper to resolve a list of paths."""
    return [resolve_path(p) for p in paths]

def get_base_dir() -> Path:
    """Returns the base repository directory."""
    return Path(__file__).resolve().parent.parent

def get_data_dir() -> Path:
    """Returns the data directory for persistent database, cache, and logs."""
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        p = Path(data_dir_env)
    else:
        p = get_base_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_reports_dir() -> Path:
    """Returns the directory where reports should be saved."""
    reports_dir_env = os.environ.get("REPORTS_DIR")
    if reports_dir_env:
        p = Path(reports_dir_env)
    else:
        p = get_data_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_cache_dir() -> Path:
    """Returns the directory for pickle and hash caches."""
    p = get_data_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p

def is_dry_run_requested(default: bool = True) -> bool:
    """
    Checks if Dry Run mode was requested via CLI flag or environment variable.
    Command-line flags override environment variables.
    """
    if "--dry-run" in sys.argv:
        return True
    if "--live" in sys.argv:
        return False
    if "DRY_RUN" in os.environ:
        val = os.environ["DRY_RUN"].strip().lower()
        return val in ("1", "true", "yes", "y")
    return default

def should_auto_confirm() -> bool:
    """
    Checks if prompts should be automatically confirmed (non-interactive mode).
    True if --yes / -y passed, AUTO_CONFIRM=1, or running without an interactive TTY.
    """
    if "--yes" in sys.argv or "-y" in sys.argv:
        return True
    if os.environ.get("AUTO_CONFIRM", "").strip().lower() in ("1", "true", "yes", "y"):
        return True
    # If stdin is not a TTY (running under background subprocess/docker), auto-confirm
    try:
        if not sys.stdin.isatty():
            return True
    except Exception:
        return True
    return False

def prompt_confirmation(prompt_text: str = "Proceed? (y/n): ") -> bool:
    """
    Prompts user for y/n confirmation.
    If running non-interactively or auto-confirm is enabled, returns True immediately.
    """
    if should_auto_confirm():
        print(f"[AUTO-CONFIRM] {prompt_text} -> 'y'")
        return True
    try:
        user_val = input(prompt_text).strip().lower()
        return user_val in ("y", "yes")
    except EOFError:
        print(f"[EOF DETECTED] Automatically proceeding.")
        return True

import os
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel
from shared.config import get_base_dir

class ScriptInfo(BaseModel):
    id: str
    name: str
    category: str
    description: str
    file_path: str  # Relative to repo root
    supports_dry_run: bool = True
    is_report_only: bool = False
    expected_reports: List[str] = []
    tags: List[str] = []

# Predefined curated metadata for all primary manga scripts
DEFAULT_SCRIPTS: Dict[str, ScriptInfo] = {
    "check_new_manga": ScriptInfo(
        id="check_new_manga",
        name="Check New Manga from Source",
        category="Check Manga",
        description="Scans Mihon downloads against your categorized library to find missing manga series and outputs a missing report.",
        file_path="Check Manga/Check_new_Manga_from_source.py",
        supports_dry_run=False,
        is_report_only=True,
        expected_reports=["missing_manga_report.txt"],
        tags=["Scan", "Report", "Mihon", "Missing"]
    ),
    "manga_folder_duplicates": ScriptInfo(
        id="manga_folder_duplicates",
        name="Manga Folder Duplicate & Hash Comparison",
        category="Check Manga",
        description="Vectorized perceptual image hashing across 12 manga library categories to detect duplicate chapters and subset releases.",
        file_path="Check Manga/Manga_Folder_Comparison_Duplicates.py",
        supports_dry_run=False,
        is_report_only=True,
        expected_reports=["Master_Manga_Duplicate_Report.xlsx"],
        tags=["Hash", "Perceptual", "Duplicates", "Excel"]
    ),
    "check_comicinfo_manga": ScriptInfo(
        id="check_comicinfo_manga",
        name="Normalize Manga ComicInfo Series",
        category="ComicInfo_Update",
        description="Scans unpacked manga folders and unifies discrepancies in ComicInfo.xml <Series> tags to the most commonly used title.",
        file_path="ComicInfo_Update/Check_ComicInfo_Manga.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=["normalization_report.txt"],
        tags=["ComicInfo", "Metadata", "Normalization", "Folder"]
    ),
    "check_comicinfo_manga_choice": ScriptInfo(
        id="check_comicinfo_manga_choice",
        name="Normalize Manga ComicInfo (Auto / Interactive Choice)",
        category="ComicInfo_Update",
        description="Finds ComicInfo.xml series naming conflicts across manga folders and unifies them to the target choice.",
        file_path="ComicInfo_Update/Check_ComicInfo_Manga_user_choice_2.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=["normalization_report.txt"],
        tags=["ComicInfo", "Interactive", "Normalization"]
    ),
    "check_comicinfo_manhwa_cbz": ScriptInfo(
        id="check_comicinfo_manhwa_cbz",
        name="Normalize Manhwa CBZ ComicInfo Series",
        category="ComicInfo_Update",
        description="Reads inside .cbz archives across Manhwa libraries and normalizes ComicInfo.xml <Series> tags to the primary name.",
        file_path="ComicInfo_Update/Check_ComicInfo_Manhwa_CBZ.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=["normalization_report_manhwa.txt"],
        tags=["ComicInfo", "CBZ", "Manhwa", "Normalization"]
    ),
    "check_comicinfo_manhwa_cbz_choice": ScriptInfo(
        id="check_comicinfo_manhwa_cbz_choice",
        name="Normalize Manhwa CBZ ComicInfo (Choice)",
        category="ComicInfo_Update",
        description="Resolves ComicInfo.xml naming conflicts inside Manhwa .cbz archives.",
        file_path="ComicInfo_Update/Check_ComicInfo_Manhwa_CBZ_user_choice_2.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=["normalization_report_manhwa.txt"],
        tags=["ComicInfo", "CBZ", "Manhwa"]
    ),
    "update_comicinfo_newfolder": ScriptInfo(
        id="update_comicinfo_newfolder",
        name="Auto-Format NewFolder ComicInfo CBZ",
        category="ComicInfo_Update",
        description="Multi-threaded auto-formatter for Title and Series tags in ComicInfo.xml for newly created CBZ archives.",
        file_path="ComicInfo_Update/Update_ComicInfo_NewFolder.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=["cbz_dry_run_report.txt", "cbz_update_report.txt"],
        tags=["ComicInfo", "NewFolder", "Auto-Format", "CBZ"]
    ),
    "convert_to_cbz": ScriptInfo(
        id="convert_to_cbz",
        name="Convert Leaf Folders to CBZ",
        category="Conver to CBZ",
        description="Compresses image folders into CBZ archives, strictly verifies output byte size, and deletes source folders.",
        file_path="Conver to CBZ/Convert_to_CBZ.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=[],
        tags=["Convert", "Compress", "CBZ", "Archive"]
    ),
    "copy_manga_folder": ScriptInfo(
        id="copy_manga_folder",
        name="Sync Mihon Folders to Categorized",
        category="Copy Manga",
        description="Copies newly downloaded Mihon chapter folders to their matching destination manga library folders.",
        file_path="Copy Manga/Copy_Manga_Folder.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=[],
        tags=["Sync", "Mihon", "Copy", "Folder"]
    ),
    "copy_manhwa_cbz": ScriptInfo(
        id="copy_manhwa_cbz",
        name="Sync Mihon CBZs to Categorized",
        category="Copy Manga",
        description="Copies newly downloaded Mihon .cbz files to their matching destination library folders.",
        file_path="Copy Manga/Copy_Manhwa_CBZ.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=[],
        tags=["Sync", "Mihon", "Copy", "CBZ"]
    ),
    "mirror_manga_to_cbz": ScriptInfo(
        id="mirror_manga_to_cbz",
        name="Mirror Manga Folders to CBZ Library",
        category="Copy Manga",
        description="Converts unpacked manga folders to mirrored CBZ archives and cleans up deleted or orphaned archives.",
        file_path="Copy Manga/Mirror_Manga_to_CBZ_2.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=[],
        tags=["Mirror", "Sync", "CBZ", "Manga"]
    ),
    "mirror_newfolder_to_cbz": ScriptInfo(
        id="mirror_newfolder_to_cbz",
        name="Mirror NewFolder to CBZ Library",
        category="Copy Manga",
        description="Synchronizes image folders from NewFolder into mirrored CBZ archive destination, removing orphaned archives.",
        file_path="Copy Manga/Mirror_NewFolder_to_CBZ.py",
        supports_dry_run=True,
        is_report_only=False,
        expected_reports=[],
        tags=["Mirror", "Sync", "CBZ", "NewFolder"]
    ),
    "duplicate_newfolder_pickle": ScriptInfo(
        id="duplicate_newfolder_pickle",
        name="Check NewFolder Duplicates (xxHash Cache)",
        category="Duplicate Check",
        description="Ultra-fast xxHash image comparison with persistent pickle caching to detect exact duplicates and partial subsets.",
        file_path="Duplicate Check/Check_Duplicate_NewFolder_2_with_pickle_memory.py",
        supports_dry_run=False,
        is_report_only=True,
        expected_reports=["manga_comparison_report.xlsx"],
        tags=["Duplicate", "xxHash", "Cache", "Excel"]
    ),
    "duplicate_name_check_all": ScriptInfo(
        id="duplicate_name_check_all",
        name="Duplicate Chapter Name Check (All Libraries)",
        category="Duplicate Check",
        description="Scans all 23 manga/manhwa library paths, parses chapter numbering and fractional releases, and outputs duplicate reports.",
        file_path="Duplicate Check/Duplicate_Name_Check_All.py",
        supports_dry_run=False,
        is_report_only=True,
        expected_reports=["All_Chapters_Verification.xlsx", "Duplicate_Chapters_Report.xlsx"],
        tags=["Duplicate", "Regex", "Report", "Excel"]
    ),
}

def get_registered_scripts() -> Dict[str, ScriptInfo]:
    """Returns all scripts, merging predefined list with any auto-discovered scripts."""
    base_dir = get_base_dir()
    registry = dict(DEFAULT_SCRIPTS)
    
    # Auto-discover any new .py scripts in category directories
    ignored_dirs = {"mangarunner", "shared", "For_Reference_Only", ".git", "venv", "__pycache__", "data", "reports", "scratch", "tests"}
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
        rel_root = os.path.relpath(root, base_dir)
        first_part = rel_root.split(os.sep)[0]
        if first_part in ignored_dirs or rel_root in ignored_dirs or first_part.startswith("."):
            continue
            
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                rel_path = os.path.join(rel_root, file).replace("\\", "/")
                # Check if already registered
                found = any(s.file_path.replace("\\", "/") == rel_path for s in registry.values())
                if not found:
                    category = os.path.basename(root)
                    script_slug = file.replace(".py", "").lower().replace(" ", "_")
                    registry[script_slug] = ScriptInfo(
                        id=script_slug,
                        name=file.replace(".py", "").replace("_", " ").title(),
                        category=category,
                        description=f"Auto-discovered script in {category}",
                        file_path=rel_path,
                        supports_dry_run=True,
                        is_report_only=False,
                        expected_reports=[],
                        tags=["Auto-Discovered"]
                    )
                    
    return registry

def get_script_by_id(script_id: str) -> Optional[ScriptInfo]:
    scripts = get_registered_scripts()
    return scripts.get(script_id)

def get_scripts_by_category() -> Dict[str, List[ScriptInfo]]:
    scripts = get_registered_scripts()
    by_cat: Dict[str, List[ScriptInfo]] = {}
    for s in scripts.values():
        by_cat.setdefault(s.category, []).append(s)
    return by_cat


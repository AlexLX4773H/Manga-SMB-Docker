import os
import sys
import shutil
import subprocess
from pathlib import Path

# Ensure shared configuration is available
_PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from shared.config import resolve_path, is_dry_run_requested

def authenticate_smb(share_path, username, password):
    if os.name != "nt":
        return
    print(f"Authenticating with network share {share_path}...")
    cmd = f'net use "{share_path}" "{password}" /user:"{username}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0 or "multiple connections" in result.stderr.lower():
        print("Successfully authenticated (or already connected).\n")
    else:
        print(f"Warning/Error during authentication: {result.stderr.strip()}")
        print("Attempting to proceed anyway...\n")

def sync_mihon_to_categorized(source_dir, dest_dir, dry_run=True):
    source_root = Path(source_dir)
    dest_root = Path(dest_dir)

    if not source_root.exists() or not dest_root.exists():
        print(f"Error: Could not find the Source or Destination on the network.")
        print(f"Source: {source_root} (exists: {source_root.exists()})")
        print(f"Dest:   {dest_root} (exists: {dest_root.exists()})")
        return

    print("Mapping Mihon source directory...")
    source_mangas = {}
    for provider_dir in source_root.iterdir():
        if provider_dir.is_dir():
            for manga_dir in provider_dir.iterdir():
                if manga_dir.is_dir():
                    source_mangas[manga_dir.name] = manga_dir

    print(f"Found {len(source_mangas)} manga series in Mihon source.\n")
    print("Scanning categorized destination for matches and copying new CBZ files...\n")

    files_copied = 0

    for root, dirs, files in os.walk(dest_root):
        root_path = Path(root)
        manga_name = root_path.name

        if manga_name in source_mangas:
            source_manga_path = source_mangas[manga_name]

            for chapter_file in source_manga_path.iterdir():
                if chapter_file.is_file() and chapter_file.suffix.lower() == '.cbz':
                    dest_chapter_path = root_path / chapter_file.name

                    if not dest_chapter_path.exists():
                        print(f"[NEW] Copying: {manga_name} -> {chapter_file.name}")
                        
                        if not dry_run:
                            shutil.copy2(chapter_file, dest_chapter_path)
                            
                        files_copied += 1

            dirs.clear()

    print("-" * 40)
    if dry_run:
        print(f"[DRY RUN COMPLETE] {files_copied} CBZ files would be copied.")
    else:
        print(f"[SYNC COMPLETE] Successfully copied {files_copied} new CBZ files.")

if __name__ == "__main__":
    SOURCE_DIRECTORY = resolve_path(r"Z:\Backup3\Mihon\downloads")
    DESTINATION_DIRECTORY = resolve_path(r"Z:\Manga")

    is_dry = is_dry_run_requested(default=True)
    if is_dry:
        print("\n--- DRY RUN INITIATED: No files will be moved or copied ---")
    else:
        print("\n--- LIVE RUN INITIATED: Files will be copied ---")

    sync_mihon_to_categorized(SOURCE_DIRECTORY, DESTINATION_DIRECTORY, dry_run=is_dry)

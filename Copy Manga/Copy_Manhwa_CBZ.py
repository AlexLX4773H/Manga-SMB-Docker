import os
import shutil
import subprocess
from pathlib import Path

def authenticate_smb(share_path, username, password):
    print(f"Authenticating with network share {share_path}...")
    # Windows command to authenticate a network share
    cmd = f'net use "{share_path}" "{password}" /user:"{username}"'
    
    # Run the command silently
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
        print(f"Please check if the paths are correct and the share is accessible.")
        return

    print("Mapping Mihon source directory...")
    # 1. Map existing Manga folders in the Source (Mihon).
    # Expected Mihon structure: downloads / Provider (e.g., AllManga) / Manga Name
    source_mangas = {}
    for provider_dir in source_root.iterdir():
        if provider_dir.is_dir():
            for manga_dir in provider_dir.iterdir():
                if manga_dir.is_dir():
                    source_mangas[manga_dir.name] = manga_dir

    print(f"Found {len(source_mangas)} manga series in Mihon source.\n")
    print("Scanning categorized destination for matches and copying new CBZ files...\n")

    files_copied = 0

    # 2. Walk the Destination directory (Categorized) to find matching Manga folders.
    for root, dirs, files in os.walk(dest_root):
        root_path = Path(root)
        manga_name = root_path.name

        # If the current destination folder matches a Manga in the Mihon source
        if manga_name in source_mangas:
            source_manga_path = source_mangas[manga_name]

            # Iterate through the files in the Mihon source
            for chapter_file in source_manga_path.iterdir():
                
                # Check if it's a file and specifically a .cbz
                if chapter_file.is_file() and chapter_file.suffix.lower() == '.cbz':
                    dest_chapter_path = root_path / chapter_file.name

                    # If this specific CBZ is missing in the destination, copy it over
                    if not dest_chapter_path.exists():
                        print(f"[NEW] Copying: {manga_name} -> {chapter_file.name}")
                        
                        if not dry_run:
                            # shutil.copy2 preserves original file metadata (timestamps)
                            shutil.copy2(chapter_file, dest_chapter_path)
                            
                        files_copied += 1

            # Clear dirs so os.walk doesn't needlessly traverse inside sub-folders in the destination
            # This makes scanning the network share drastically faster.
            dirs.clear()

    print("-" * 40)
    if dry_run:
        print(f"[DRY RUN COMPLETE] {files_copied} CBZ files would be copied.")
        print("To execute the copy, change 'dry_run=False' in the function call at the bottom.")
    else:
        print(f"[SYNC COMPLETE] Successfully copied {files_copied} new CBZ files.")

if __name__ == "__main__":

    # --- NETWORK PATHS ---
    # Updated to the new Backup3 path
    SOURCE_DIRECTORY = r"Z:\Backup3\Mihon\downloads"
    DESTINATION_DIRECTORY = r"Z:\Manga"

    # Set dry_run=True to test what will be copied without moving any files.
    # Set dry_run=False to actually copy the files over the network.
    sync_mihon_to_categorized(SOURCE_DIRECTORY, DESTINATION_DIRECTORY, dry_run=False)
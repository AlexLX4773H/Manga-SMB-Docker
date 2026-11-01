import os
import subprocess
from pathlib import Path

def authenticate_smb(share_path, username, password):
    print(f"Authenticating with network share {share_path}...")
    cmd = f'net use "{share_path}" "{password}" /user:"{username}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0 or "multiple connections" in result.stderr.lower():
        print("Successfully authenticated (or already connected).\n")
    else:
        print(f"Warning/Error during authentication: {result.stderr.strip()}")
        print("Attempting to proceed anyway...\n")

def generate_missing_manga_report(source_dirs, dest_dir, report_file_path):
    dest_root = Path(dest_dir)

    if not dest_root.exists():
        print(f"Error: Could not find the Destination on the network: {dest_dir}")
        return

    # Map source mangas. 
    # Stored as: { "Exact Manga Name": "Provider Name" }
    source_mangas = {}
    
    print("Scanning source directories...")
    # Loop through the list of source directories
    for src in source_dirs:
        source_root = Path(src)
        
        if not source_root.exists():
            print(f"  [!] Warning: Source directory not found, skipping -> {src}")
            continue
            
        print(f"  -> Scanning: {src}")
        for provider_dir in source_root.iterdir():
            if provider_dir.is_dir():
                for manga_dir in provider_dir.iterdir():
                    if manga_dir.is_dir():
                        # Save the exact name and the provider for the report
                        source_mangas[manga_dir.name] = provider_dir.name

    print(f"\nFound {len(source_mangas)} unique manga series across all sources.\n")
    
    print("Scanning categorized destination library (this may take a moment)...")
    # Collect all folder names in the destination tree using exact casing
    dest_folder_names = set()
    for root, dirs, files in os.walk(dest_root):
        for d in dirs:
            dest_folder_names.add(d)

    print(f"Found {len(dest_folder_names)} total folders in destination.\n")
    print("Comparing libraries...")

    # Find what's missing (Case-Sensitive Comparison)
    missing_mangas = []
    for manga_name, provider in source_mangas.items():
        if manga_name not in dest_folder_names:
            missing_mangas.append((manga_name, provider))

    # Sort the missing manga alphabetically by exact name
    missing_mangas.sort(key=lambda x: x[0])

    # --- OUTPUT THE REPORT ---
    print("-" * 40)
    if not missing_mangas:
        print("Great news! All manga in your sources exist in your categorized library.")
    else:
        print(f"Found {len(missing_mangas)} missing manga series. Generating report...")
        
        # Write to console and to file
        with open(report_file_path, "w", encoding="utf-8") as f:
            f.write(f"--- MISSING MANGA REPORT ---\n")
            f.write(f"Total Missing: {len(missing_mangas)}\n\n")
            
            for manga_name, provider in missing_mangas:
                line = f"[{provider}] {manga_name}"
                print(line)
                f.write(line + "\n")
                
        print("-" * 40)
        print(f"Report successfully saved to: {report_file_path}")

if __name__ == "__main__":

    # Define a list of source directories to scan
    SOURCE_DIRECTORIES = [
        r"Z:\Backup2\Vere\Mihon\downloads",
        r"Z:\Backup3\Mihon\downloads"
    ]
    
    DESTINATION_DIRECTORY = r"Z:\Manga"
    
    # --- REPORT PATH ---
    REPORT_FILE = "missing_manga_report.txt"

    generate_missing_manga_report(SOURCE_DIRECTORIES, DESTINATION_DIRECTORY, REPORT_FILE)
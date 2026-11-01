import os
import sys
import time
import concurrent.futures
from datetime import datetime
from collections import defaultdict
import pandas as pd
import xxhash
import pickle

# Ensure shared configuration is available
_PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from shared.config import resolve_path, get_reports_dir, get_cache_dir

# --- Configuration ---
MAPPED_DRIVE_PATH = resolve_path(r"Z:\Backup2\Vere\NewFolder")
EXCEL_OUTPUT = str(get_reports_dir() / "manga_comparison_report.xlsx")
CACHE_FILE = str(get_cache_dir() / "manga_hash_cache.pkl")

# Image extensions to look for
VALID_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.gif'}

def get_file_hash(file_path):
    """Generates a fast xxhash for a file using native OS reading."""
    x = xxhash.xxh64()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                x.update(chunk)
        return x.hexdigest()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

def analyze_leaf_folder(folder_path):
    """Hashes all images in a leaf folder."""
    start_time = time.time()
    
    hashes = set()
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file() and any(entry.name.lower().endswith(ext) for ext in VALID_EXTS):
                    file_hash = get_file_hash(entry.path)
                    if file_hash:
                        hashes.add(file_hash)
    except Exception as e:
        print(f"Error accessing directory {folder_path}: {e}")
                
    time_taken = round(time.time() - start_time, 4)
    return folder_path, hashes, time_taken

def check_match(set_a, set_b):
    """Checks if sets are identical or subsets based on the tolerance rule."""
    len_a, len_b = len(set_a), len(set_b)
    if len_a == 0 or len_b == 0:
        return None

    common = len(set_a.intersection(set_b))
    
    diff_a = len_a - common
    diff_b = len_b - common
    
    pct_diff_a = diff_a / len_a
    pct_diff_b = diff_b / len_b
    
    a_is_subset = (diff_a <= 2 and pct_diff_a <= 0.10)
    b_is_subset = (diff_b <= 2 and pct_diff_b <= 0.10)
    
    if a_is_subset and b_is_subset:
        return "Identical"
    elif a_is_subset:
        return "Subset: Folder A is a subset of Folder B"
    elif b_is_subset:
        return "Subset: Folder B is a subset of Folder A"
    return None

def main():
    # --- 1. Load Cache ---
    cache = {}
    if os.path.exists(CACHE_FILE):
        print(f"Loading cache from {CACHE_FILE}...")
        try:
            with open(CACHE_FILE, 'rb') as f:
                cache = pickle.load(f)
            print(f"Loaded {len(cache)} cached folders.")
        except Exception as e:
            print(f"Error loading cache (corrupted?). Starting fresh. Error: {e}")

    print(f"Scanning directory tree at {MAPPED_DRIVE_PATH} to find leaf folders...")
    if not os.path.exists(MAPPED_DRIVE_PATH):
        print(f"Error: Path {MAPPED_DRIVE_PATH} does not exist or is not mounted.")
        return

    leaf_folders = {}
    for root, dirs, files in os.walk(MAPPED_DRIVE_PATH):
        if not dirs and files:
            leaf_folders[root] = os.stat(root).st_mtime

    print(f"Found {len(leaf_folders)} leaf folders.")
    
    folder_data = {}
    analysis_stats = []
    folders_to_hash = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- 2. Check Cache Validity ---
    print("Checking cache validity...")
    for folder, mtime in leaf_folders.items():
        if folder in cache and cache[folder]['mtime'] == mtime:
            folder_data[folder] = cache[folder]['hashes']
            analysis_stats.append({
                "Folder Path": folder,
                "Total Images": len(cache[folder]['hashes']),
                "Analysis Timestamp": timestamp,
                "Time Taken (Seconds)": 0.0,
                "Status": "Loaded from Cache"
            })
        else:
            folders_to_hash.append(folder)

    # --- 3. Process Only Uncached/Modified Folders ---
    if folders_to_hash:
        print(f"Hashing {len(folders_to_hash)} new or modified folders...")
        workers = min(16, max(1, os.cpu_count() or 4))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(analyze_leaf_folder, folder): folder for folder in folders_to_hash}
            
            for future in concurrent.futures.as_completed(futures):
                folder_path, hashes, time_taken = future.result()
                if hashes:
                    folder_data[folder_path] = hashes
                    cache[folder_path] = {
                        'hashes': hashes,
                        'mtime': leaf_folders[folder_path]
                    }
                
                analysis_stats.append({
                    "Folder Path": folder_path,
                    "Total Images": len(hashes),
                    "Analysis Timestamp": timestamp,
                    "Time Taken (Seconds)": time_taken,
                    "Status": "Newly Hashed"
                })
                print(f"Hashed: {folder_path} | Images: {len(hashes)} | Time: {time_taken}s")
    else:
        print("No new or modified folders to hash. All data loaded from cache!")

    # --- 4. Prune Cache (Remove deleted folders) ---
    stale_folders = [f for f in cache.keys() if f not in leaf_folders]
    for stale in stale_folders:
        del cache[stale]
    
    print(f"Saving updated cache to {CACHE_FILE}...")
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache, f)
    except Exception as e:
        print(f"Warning: Failed to save cache: {e}")

    # --- 5. Comparison Logic ---
    print("\nBuilding inverted index for fast comparison...")
    hash_to_folders = defaultdict(list)
    for folder, hashes in folder_data.items():
        for h in hashes:
            hash_to_folders[h].append(folder)
            
    pairs_to_check = set()
    for folders in hash_to_folders.values():
        if len(folders) > 1:
            for i in range(len(folders)):
                for j in range(i + 1, len(folders)):
                    pair = tuple(sorted([folders[i], folders[j]]))
                    pairs_to_check.add(pair)

    print(f"Evaluating {len(pairs_to_check)} potential folder matches...")
    
    comparison_results = []
    for folder_a, folder_b in pairs_to_check:
        status = check_match(folder_data[folder_a], folder_data[folder_b])
        if status:
            comparison_results.append({
                "Folder A": folder_a,
                "Folder B": folder_b,
                "Status": status,
                "Folder A Image Count": len(folder_data[folder_a]),
                "Folder B Image Count": len(folder_data[folder_b])
            })

    # --- 6. Write to Excel ---
    print("\nWriting reports to Excel...")
    try:
        with pd.ExcelWriter(EXCEL_OUTPUT, engine='openpyxl') as writer:
            if comparison_results:
                df_results = pd.DataFrame(comparison_results)
                df_results.to_excel(writer, sheet_name='Matches & Subsets', index=False)
            else:
                pd.DataFrame({"Message": ["No matches or subsets found."]}).to_excel(writer, sheet_name='Matches & Subsets', index=False)
                
            df_stats = pd.DataFrame(analysis_stats)
            df_stats.to_excel(writer, sheet_name='Leaf Analysis Stats', index=False)
            
        print(f"Done! Report saved to {EXCEL_OUTPUT}")
    except Exception as e:
        print(f"Error writing Excel output: {e}")

if __name__ == "__main__":
    main()

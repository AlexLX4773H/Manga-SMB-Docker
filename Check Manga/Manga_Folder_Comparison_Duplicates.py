import os
import time
from datetime import datetime
from itertools import combinations
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
from PIL import Image
import imagehash

# ==========================================
# Configuration
# ==========================================
TARGET_PATHS = [
    r"Z:\Manga\Manga_1\Axe",
    r"Z:\Manga\Manga_1\Completed",
    r"Z:\Manga\Manga_1\Completed Current3",
    r"Z:\Manga\Manga_1\Current",
    r"Z:\Manga\Manga_1\Current Axe4",
    r"Z:\Manga\Manga_1\Current Old5",
    r"Z:\Manga\Manga_A2\Axe",
    r"Z:\Manga\Manga_A2\Completed",
    r"Z:\Manga\Manga_A2\Completed Current3",
    r"Z:\Manga\Manga_A2\Current",
    r"Z:\Manga\Manga_A2\Current Axe4",
    r"Z:\Manga\Manga_A2\Current Old5"
]

EXCEL_OUTPUT_NAME = "Master_Manga_Duplicate_Report.xlsx"
NUM_WORKERS = 16  # Tailored for your 16-thread processor

# ==========================================

def _hash_single_image(filepath):
    """Worker task: Opens an image and calculates its perceptual hash binary array."""
    try:
        with Image.open(filepath) as img:
            # We extract the underlying boolean array directly for blazing fast matrix comparison later
            return filepath, imagehash.phash(img).hash.flatten()
    except Exception:
        return filepath, None

def get_image_hashes_parallel(folder_path, executor):
    """Dispatches folder files to the process pool for parallelized decoding/hashing."""
    valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
    filepaths = []
    
    try:
        for filename in os.listdir(folder_path):
            if os.path.splitext(filename)[1].lower() in valid_extensions:
                filepaths.append(os.path.join(folder_path, filename))
    except PermissionError:
        print(f"Permission denied to read: {folder_path}")
        return None
    except FileNotFoundError:
        print(f"Path not found (check Z: drive connection): {folder_path}")
        return None

    if not filepaths:
        return None

    # Map the files to our multi-process worker pool
    results = executor.map(_hash_single_image, filepaths, chunksize=4)
    
    # Store hashes as flat boolean matrices
    hash_matrix = []
    for filepath, h_array in results:
        if h_array is not None:
            hash_matrix.append(h_array)
            
    if not hash_matrix:
        return None
        
    return np.array(hash_matrix, dtype=bool)

def compare_hash_matrices(series_name, name_a, matrix_a, name_b, matrix_b, root_location, hash_tolerance=4, max_mismatch_ratio=0.10):
    """Uses vectorized matrix math to compare all image hashes simultaneously in microseconds."""
    len_a = len(matrix_a)
    len_b = len(matrix_b)
    
    # Fast Hamming distance calculation via matrix broadcasting:
    # matrix_a[:, None, :] creates an axis to compare every element of A to every element of B.
    # .sum(axis=2) calculates the bitwise differences (Hamming distance) across the flat image hashes.
    hamming_distances = (matrix_a[:, None, :] != matrix_b[None, :, :]).sum(axis=2)

    # For each image in A, find if there is ANY match in B within tolerance bounds
    matched_a = np.sum(np.any(hamming_distances <= hash_tolerance, axis=1))
    # For each image in B, find if there is ANY match in A within tolerance bounds
    matched_b = np.sum(np.any(hamming_distances <= hash_tolerance, axis=0))

    mismatched_a = len_a - matched_a
    mismatched_b = len_b - matched_b

    thresh_a = len_a * max_mismatch_ratio
    thresh_b = len_b * max_mismatch_ratio

    a_is_subset = mismatched_a <= thresh_a
    b_is_subset = mismatched_b <= thresh_b

    if a_is_subset and b_is_subset:
        status = "SAME"
    elif a_is_subset and not b_is_subset:
        status = "SUBSET (A is inside B)"
    elif b_is_subset and not a_is_subset:
        status = "SUBSET (B is inside A)"
    else:
        return None 

    return {
        "Root Location": root_location,
        "Series": series_name,
        "Status": status,
        "Folder A": name_a,
        "Folder B": name_b,
        "Images in A": len_a,
        "Images in B": len_b,
        "Missing in A": int(mismatched_b), 
        "Missing in B": int(mismatched_a),
        "Allowed Missing (10%)": f"A:{int(thresh_a)} | B:{int(thresh_b)}"
    }

def scan_library(root_dir, executor):
    """Scans a library tree using vector math and process pooling."""
    manga_groups = {}
    report_data = [] 
    
    valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        has_images = any(os.path.splitext(f)[1].lower() in valid_extensions for f in filenames)
        if has_images:
            parent_dir = os.path.dirname(dirpath)
            manga_groups.setdefault(parent_dir, []).append(dirpath)

    if not manga_groups:
        print("No image folders found in this location.")
        return report_data

    print(f"Found {len(manga_groups)} series folders containing chapters to check.\n")

    for series_path, chapter_folders in manga_groups.items():
        if len(chapter_folders) < 2:
            continue 
            
        series_name = os.path.basename(series_path)
        
        series_start_time = time.time()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Analyzing series: '{series_name}' ({len(chapter_folders)} chapters)...")
        
        # Parallel extraction of hashes for all chapters in this series
        chapter_matrices = {}
        for chapter in chapter_folders:
            matrix = get_image_hashes_parallel(chapter, executor)
            if matrix is not None:
                chapter_matrices[chapter] = matrix
            
        # Fast vectorized matrix tracking and cross-examination
        for folder_a, folder_b in combinations(chapter_matrices.keys(), 2):
            name_a = os.path.basename(folder_a)
            name_b = os.path.basename(folder_b)
            
            row_data = compare_hash_matrices(
                series_name, name_a, chapter_matrices[folder_a], 
                name_b, chapter_matrices[folder_b], root_dir
            )
            if row_data:
                report_data.append(row_data)
                
        series_duration = time.time() - series_start_time
        print(f"  -> Finished '{series_name}' in {series_duration:.2f} seconds.\n")

    return report_data

# ==========================================
# Run the script
# ==========================================
if __name__ == "__main__":
    all_report_data = []
    total_start_time = time.time()

    # Using ProcessPoolExecutor to bypass Python's Global Interpreter Lock (GIL)
    # This allows genuine utilize of your 16 CPU cores.
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        for path in TARGET_PATHS:
            print(f"\n{'='*60}")
            print(f"Starting scan for location: {path}")
            print(f"{'='*60}")
            
            path_start_time = time.time()
            
            path_data = scan_library(path, executor)
            if path_data:
                all_report_data.extend(path_data)
                
            path_duration = time.time() - path_start_time
            mins, secs = divmod(path_duration, 60)
            print(f"-> Scan for {path} completed in {int(mins)}m {secs:.2f}s.")

    # Generate Report
    print(f"\n{'='*60}")
    print("Generating Master Excel Report...")
    if all_report_data:
        df = pd.DataFrame(all_report_data)
        df = df.sort_values(by=["Root Location", "Series", "Status"])
        try:
            df.to_excel(EXCEL_OUTPUT_NAME, index=False)
            print(f"✅ Master report saved to: {os.path.abspath(EXCEL_OUTPUT_NAME)}")
        except Exception as e:
            print(f"❌ Error saving Excel file. Is it open? Error: {e}")
    else:
        print("Scan complete. No duplicates or subsets found anywhere!")

    total_duration = time.time() - total_start_time
    total_mins, total_secs = divmod(total_duration, 60)
    print(f"Total execution time across all locations: {int(total_mins)}m {total_secs:.2f}s.")
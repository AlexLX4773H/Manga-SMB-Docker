import importlib.util
import os
import sys
import time
from datetime import datetime
from itertools import combinations
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
from PIL import Image
import imagehash
import xxhash

# Ensure shared configuration is available
_PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from shared.config import resolve_paths, get_reports_dir

def _load_parse_chapter_name():
    """Reuse the chapter parser from the name-duplicate checker."""
    parser_path = os.path.join(_PARENT_DIR, "Duplicate Check", "Duplicate_Name_Check_All.py")
    spec = importlib.util.spec_from_file_location("duplicate_name_check_all", parser_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_chapter_name

parse_chapter_name = _load_parse_chapter_name()

# ==========================================
# Configuration
# ==========================================
TARGET_PATHS = resolve_paths([
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
])

VALID_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
NUM_WORKERS = min(16, max(1, os.cpu_count() or 4))

DETECTION_MODES = ("name_and_hash", "visual_similarity", "exact_hash")
DEFAULT_DETECTION_MODE = "name_and_hash"
MODE_LABELS = {
    "name_and_hash": "Name and Hash",
    "visual_similarity": "Visual Similarity",
    "exact_hash": "Exact Hash Check",
}
REPORT_FILENAMES = {
    "name_and_hash": "Master_Manga_Duplicate_Report_NameAndHash.xlsx",
    "visual_similarity": "Master_Manga_Duplicate_Report_Visual.xlsx",
    "exact_hash": "Master_Manga_Duplicate_Report_ExactHash.xlsx",
}

# ==========================================

def resolve_detection_mode(raw):
    """Unknown or empty values fall back to Name and Hash."""
    if raw is None:
        return DEFAULT_DETECTION_MODE
    value = str(raw).strip().lower()
    if value in DETECTION_MODES:
        return value
    return DEFAULT_DETECTION_MODE

def detection_mode_from_runtime(environ=None, argv=None):
    """CLI --detection-mode overrides the DETECTION_MODE environment variable."""
    environ = os.environ if environ is None else environ
    argv = sys.argv if argv is None else argv
    raw = environ.get("DETECTION_MODE")
    if "--detection-mode" in argv:
        idx = argv.index("--detection-mode")
        if idx + 1 < len(argv):
            raw = argv[idx + 1]
    return resolve_detection_mode(raw)

def chapters_share_base(name_a, name_b):
    """True when both folder names parse to the same base chapter number."""
    base_a, _frac_a = parse_chapter_name(name_a)
    base_b, _frac_b = parse_chapter_name(name_b)
    if base_a is None or base_b is None:
        return False
    return base_a == base_b

def pair_allowed(name_a, name_b, mode):
    """Name and Hash only compares chapters that share a parsed chapter number."""
    resolved = resolve_detection_mode(mode)
    if resolved == "name_and_hash":
        return chapters_share_base(name_a, name_b)
    return True

def _hash_single_image(filepath):
    """Worker task: Opens an image and calculates its perceptual hash binary array."""
    try:
        with Image.open(filepath) as img:
            return filepath, imagehash.phash(img).hash.flatten()
    except Exception:
        return filepath, None

def _xxhash_single_file(filepath):
    """Worker task: exact xxHash64 of an image file's bytes."""
    hasher = xxhash.xxh64()
    try:
        with open(filepath, "rb") as handle:
            while chunk := handle.read(8192):
                hasher.update(chunk)
        return filepath, hasher.hexdigest()
    except Exception:
        return filepath, None

def _list_image_paths(folder_path):
    filepaths = []
    try:
        for filename in os.listdir(folder_path):
            if os.path.splitext(filename)[1].lower() in VALID_EXTENSIONS:
                filepaths.append(os.path.join(folder_path, filename))
    except PermissionError:
        print(f"Permission denied to read: {folder_path}")
        return None
    except FileNotFoundError:
        print(f"Path not found (check connection/mount): {folder_path}")
        return None
    return filepaths

def get_image_hashes_parallel(folder_path, executor):
    """Dispatches folder files to the process pool for parallelized decoding/hashing."""
    filepaths = _list_image_paths(folder_path)
    if not filepaths:
        return None

    results = executor.map(_hash_single_image, filepaths, chunksize=4)

    hash_matrix = []
    for _filepath, h_array in results:
        if h_array is not None:
            hash_matrix.append(h_array)

    if not hash_matrix:
        return None

    return np.array(hash_matrix, dtype=bool)

def get_exact_hashes_parallel(folder_path, executor):
    """Exact content hashes for every image in a chapter folder."""
    filepaths = _list_image_paths(folder_path)
    if not filepaths:
        return None

    results = executor.map(_xxhash_single_file, filepaths, chunksize=8)
    hashes = set()
    for _filepath, digest in results:
        if digest:
            hashes.add(digest)
    if not hashes:
        return None
    return hashes

def compare_hash_matrices(series_name, name_a, matrix_a, name_b, matrix_b, root_location, mode_label, hash_tolerance=4, max_mismatch_ratio=0.10):
    """Uses vectorized matrix math to compare all image hashes simultaneously in microseconds."""
    len_a = len(matrix_a)
    len_b = len(matrix_b)

    hamming_distances = (matrix_a[:, None, :] != matrix_b[None, :, :]).sum(axis=2)

    matched_a = np.sum(np.any(hamming_distances <= hash_tolerance, axis=1))
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
        "Mode": mode_label,
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

def compare_exact_sets(series_name, name_a, set_a, name_b, set_b, root_location, mode_label):
    """Identical file bytes, with the same subset rule as the NewFolder xxHash checker."""
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
        status = "Identical"
    elif a_is_subset:
        status = "Subset: Folder A is a subset of Folder B"
    elif b_is_subset:
        status = "Subset: Folder B is a subset of Folder A"
    else:
        return None

    return {
        "Mode": mode_label,
        "Root Location": root_location,
        "Series": series_name,
        "Status": status,
        "Folder A": name_a,
        "Folder B": name_b,
        "Images in A": len_a,
        "Images in B": len_b,
        "Missing in A": int(diff_b),
        "Missing in B": int(diff_a),
        "Allowed Missing (10%)": "<=2 files and <=10%"
    }

def scan_library(root_dir, executor, mode):
    """Scans a library tree. Mode selects name gating and hash type."""
    mode = resolve_detection_mode(mode)
    mode_label = MODE_LABELS[mode]
    manga_groups = {}
    report_data = []

    for dirpath, _dirnames, filenames in os.walk(root_dir):
        has_images = any(os.path.splitext(f)[1].lower() in VALID_EXTENSIONS for f in filenames)
        if has_images:
            parent_dir = os.path.dirname(dirpath)
            manga_groups.setdefault(parent_dir, []).append(dirpath)

    if not manga_groups:
        print(f"No image folders found in location: {root_dir}")
        return report_data

    print(f"Found {len(manga_groups)} series folders containing chapters to check in {root_dir}.\n")

    for series_path, chapter_folders in manga_groups.items():
        if mode == "name_and_hash":
            chapter_folders = [
                chapter for chapter in chapter_folders
                if parse_chapter_name(os.path.basename(chapter))[0] is not None
            ]
        if len(chapter_folders) < 2:
            continue

        series_name = os.path.basename(series_path)

        series_start_time = time.time()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Analyzing series: '{series_name}' ({len(chapter_folders)} chapters) [{mode_label}]...")

        chapter_payloads = {}
        for chapter in chapter_folders:
            if mode == "exact_hash":
                payload = get_exact_hashes_parallel(chapter, executor)
            else:
                payload = get_image_hashes_parallel(chapter, executor)
            if payload is not None:
                chapter_payloads[chapter] = payload

        for folder_a, folder_b in combinations(chapter_payloads.keys(), 2):
            name_a = os.path.basename(folder_a)
            name_b = os.path.basename(folder_b)
            if not pair_allowed(name_a, name_b, mode):
                continue

            if mode == "exact_hash":
                row_data = compare_exact_sets(
                    series_name, name_a, chapter_payloads[folder_a],
                    name_b, chapter_payloads[folder_b], root_dir, mode_label
                )
            else:
                row_data = compare_hash_matrices(
                    series_name, name_a, chapter_payloads[folder_a],
                    name_b, chapter_payloads[folder_b], root_dir, mode_label
                )
            if row_data:
                report_data.append(row_data)

        series_duration = time.time() - series_start_time
        print(f"  -> Finished '{series_name}' in {series_duration:.2f} seconds.\n")

    return report_data

def report_path_for_mode(mode):
    resolved = resolve_detection_mode(mode)
    return str(get_reports_dir() / REPORT_FILENAMES[resolved])

def main():
    mode = detection_mode_from_runtime()
    mode_label = MODE_LABELS[mode]
    excel_output = report_path_for_mode(mode)
    print(f"Detection mode: {mode_label}")

    all_report_data = []
    total_start_time = time.time()

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        for path in TARGET_PATHS:
            print(f"\n{'='*60}")
            print(f"Starting scan for location: {path}")
            print(f"{'='*60}")

            path_start_time = time.time()

            path_data = scan_library(path, executor, mode)
            if path_data:
                all_report_data.extend(path_data)

            path_duration = time.time() - path_start_time
            mins, secs = divmod(path_duration, 60)
            print(f"-> Scan for {path} completed in {int(mins)}m {secs:.2f}s.")

    print(f"\n{'='*60}")
    print(f"Generating {mode_label} Excel Report...")
    if all_report_data:
        df = pd.DataFrame(all_report_data)
        df = df.sort_values(by=["Root Location", "Series", "Status"])
        try:
            df.to_excel(excel_output, index=False)
            print(f"Master report saved to: {os.path.abspath(excel_output)}")
        except Exception as e:
            print(f"Error saving Excel file. Is it open? Error: {e}")
    else:
        print("Scan complete. No duplicates or subsets found anywhere!")

    total_duration = time.time() - total_start_time
    total_mins, total_secs = divmod(total_duration, 60)
    print(f"Total execution time across all locations: {int(total_mins)}m {total_secs:.2f}s.")

if __name__ == "__main__":
    main()

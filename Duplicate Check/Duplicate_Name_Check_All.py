import os
import sys
import re
import zipfile
import pandas as pd

# Ensure shared configuration is available
_PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from shared.config import resolve_paths, get_reports_dir

def get_image_count(item_path):
    """
    Counts image files within a standard directory or a CBZ archive.
    """
    image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.bmp', '.gif'}
    count = 0
    try:
        if os.path.isdir(item_path):
            for root, _, files in os.walk(item_path):
                for file in files:
                    if os.path.splitext(file)[1].lower() in image_exts:
                        count += 1
                        
        elif zipfile.is_zipfile(item_path):
            with zipfile.ZipFile(item_path, 'r') as z:
                for name in z.namelist():
                    if os.path.splitext(name)[1].lower() in image_exts:
                        count += 1
    except Exception as e:
        print(f"Error reading {item_path}: {e}")
        
    return count

def parse_chapter_name(name):
    """
    Extracts the base chapter and fractional part.
    Matches formats like 'Chapter 7.1_abc', 'Ch. 7', 'Vol.1 Ch. 2.5', or standalone '3.1_xxx'.
    """
    match = re.search(r'(?:ch(?:apter|\.)?)\s*(\d+)(?:\.(\d+))?', name, re.IGNORECASE)
    if match:
        base = int(match.group(1))
        frac = int(match.group(2)) if match.group(2) else 0
        return base, frac

    match = re.search(r'(?<!\d)(\d+)(?:\.(\d+))?_', name)
    if match:
        base = int(match.group(1))
        frac = int(match.group(2)) if match.group(2) else 0
        return base, frac

    match = re.search(r'(?<!\d)(\d+)(?:\.(\d+))?', name)
    if match:
        base = int(match.group(1))
        frac = int(match.group(2)) if match.group(2) else 0
        return base, frac

    return None, None

def find_duplicate_chapters(library_paths, margin=5):
    """
    Scans a list of library paths.
    Returns two lists: one for the duplicates, and one logging every chapter scanned for verification.
    """
    duplicate_data = []
    all_chapters_log = []

    for library_path in library_paths:
        if not os.path.exists(library_path):
            print(f"Warning: The path '{library_path}' does not exist. Skipping.")
            continue

        for manga_name in os.listdir(library_path):
            manga_path = os.path.join(library_path, manga_name)
            if not os.path.isdir(manga_path):
                continue

            base_chapters = {}
            frac_chapters = {}

            for chapter_entry in os.listdir(manga_path):
                chapter_path = os.path.join(manga_path, chapter_entry)
                
                is_cbz = chapter_path.lower().endswith('.cbz')
                if not (os.path.isdir(chapter_path) or is_cbz):
                    continue

                base, frac = parse_chapter_name(chapter_entry)
                
                all_chapters_log.append({
                    'Library Location': library_path,
                    'Manga Title': manga_name,
                    'Original Name': chapter_entry,
                    'Format': 'CBZ' if is_cbz else 'Folder',
                    'Parsed Base Chapter': base if base is not None else 'Unrecognized',
                    'Parsed Fraction': frac if frac is not None else 'Unrecognized'
                })

                if base is None:
                    continue

                if frac == 0:
                    base_chapters[base] = chapter_path
                else:
                    if base not in frac_chapters:
                        frac_chapters[base] = []
                    frac_chapters[base].append(chapter_path)

            for base, main_path in base_chapters.items():
                if base in frac_chapters:
                    sub_paths = frac_chapters[base]
                    
                    main_count = get_image_count(main_path)
                    sub_count_sum = sum(get_image_count(p) for p in sub_paths)

                    difference = abs(main_count - sub_count_sum)
                    is_match = difference <= margin

                    duplicate_data.append({
                        'Library Location': library_path,
                        'Manga Title': manga_name,
                        'Base Chapter': base,
                        'Main Chapter Name': os.path.basename(main_path),
                        'Main Image Count': main_count,
                        'Sub-Chapters': ", ".join([os.path.basename(p) for p in sub_paths]),
                        'Sub-Chapters Sum Count': sub_count_sum,
                        'Page Count Difference': difference,
                        'Duplicate Match (Tolerance <= 5)': "YES" if is_match else "NO (Differs)"
                    })

    return duplicate_data, all_chapters_log

def generate_reports(duplicate_data, all_chapters_log):
    reports_dir = get_reports_dir()
    log_report_path = str(reports_dir / "All_Chapters_Verification.xlsx")
    dupe_report_path = str(reports_dir / "Duplicate_Chapters_Report.xlsx")

    # Output 1: Verification Report
    if all_chapters_log:
        df_log = pd.DataFrame(all_chapters_log)
        df_log.to_excel(log_report_path, index=False)
        print(f"Verification report generated: {log_report_path} ({len(df_log)} files scanned)")
    else:
        print("No chapters were found during the scan.")

    # Output 2: Duplicate Report
    if not duplicate_data:
        print("No duplicates found. Your libraries are clean!")
    else:
        df_dupe = pd.DataFrame(duplicate_data)
        df_dupe.to_excel(dupe_report_path, index=False)
        print(f"Duplicate report generated: {dupe_report_path} ({len(df_dupe)} duplicates found)")

if __name__ == "__main__":
    LIBRARY_PATHS = resolve_paths([
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
        r"Z:\Manga\Manga_A2\Current Old5",
        r"Z:\Manga\Manhwa_CBZ_1\Completed Current3",
        r"Z:\Manga\Manhwa_CBZ_1\Current",
        r"Z:\Manga\Manhwa_CBZ_1\Current Axe4",
        r"Z:\Manga\Manhwa_CBZ_1\Current Old5",
        r"Z:\Manga\Manhwa_CBZ_H3\Completed Current3",
        r"Z:\Manga\Manhwa_CBZ_H3\Current",
        r"Z:\Manga\Manhwa_CBZ_H3\Current Axe4",
        r"Z:\Manga\Manhwa_CBZ_H3\Current Old5",
        r"Z:\Manga\Manhwa_CBZ_H3\Completed",
        r"Z:\Manga\Manhwa_CBZ_H3\Current U",
        r"Z:\Manga\Manhwa_CBZ_H3\Current Standard"
    ])
    
    PAGE_TOLERANCE = 5  

    print(f"Scanning {len(LIBRARY_PATHS)} library locations...")
    duplicates, scanned_log = find_duplicate_chapters(LIBRARY_PATHS, margin=PAGE_TOLERANCE)
    generate_reports(duplicates, scanned_log)

import os
import re
import zipfile
import pandas as pd

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
    # 1. Explicit Chapter/Ch keywords
    match = re.search(r'(?:ch(?:apter|\.)?)\s*(\d+)(?:\.(\d+))?', name, re.IGNORECASE)
    if match:
        base = int(match.group(1))
        frac = int(match.group(2)) if match.group(2) else 0
        return base, frac

    # 2. Fallback: number patterns typically ending with an underscore (like '3.1_e34a04')
    match = re.search(r'(?<!\d)(\d+)(?:\.(\d+))?_', name)
    if match:
        base = int(match.group(1))
        frac = int(match.group(2)) if match.group(2) else 0
        return base, frac

    # 3. Final fallback: First number sequence found in the string
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

            # Parse every chapter file/folder in the manga directory
            for chapter_entry in os.listdir(manga_path):
                chapter_path = os.path.join(manga_path, chapter_entry)
                
                # Support both standard folders and CBZ files
                is_cbz = chapter_path.lower().endswith('.cbz')
                if not (os.path.isdir(chapter_path) or is_cbz):
                    continue

                base, frac = parse_chapter_name(chapter_entry)
                
                # 1. Log every scanned chapter for the Verification Report
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

                # Ignore .5 chapters (omakes/specials) for the duplicate check
                if frac == 5:
                    continue

                img_count = get_image_count(chapter_path)
                
                chap_info = {
                    'name': chapter_entry,
                    'images': img_count,
                    'path': library_path
                }

                if frac == 0:
                    # Store the base chapter (e.g., Chapter 7)
                    if base not in base_chapters or base_chapters[base]['images'] < img_count:
                        base_chapters[base] = chap_info
                else:
                    # Group fractional chapters (e.g., Chapter 7.1, 7.2)
                    if base not in frac_chapters:
                        frac_chapters[base] = []
                    frac_chapters[base].append(chap_info)

            # 2. Check for duplicates by comparing page totals
            for base, main_chap in base_chapters.items():
                if base in frac_chapters:
                    sub_chaps = frac_chapters[base]
                    total_sub_images = sum(sub['images'] for sub in sub_chaps)
                    main_images = main_chap['images']
                    
                    # Verify if counts match within the acceptable promo-page margin
                    if abs(main_images - total_sub_images) <= margin:
                        sub_names = ", ".join([sub['name'] for sub in sub_chaps])
                        duplicate_data.append({
                            'Library Location': main_chap['path'],
                            'Manga Title': manga_name,
                            'Base Chapter': main_chap['name'],
                            'Base Pages': main_images,
                            'Sub-Chapters Included': sub_names,
                            'Sub-Chapters Total Pages': total_sub_images,
                            'Page Difference': abs(main_images - total_sub_images)
                        })

    return duplicate_data, all_chapters_log

def generate_reports(duplicate_data, all_chapters_log):
    # Output 1: Verification Report
    if all_chapters_log:
        df_log = pd.DataFrame(all_chapters_log)
        df_log.to_excel("All_Chapters_Verification.xlsx", index=False)
        print(f"Verification report generated: All_Chapters_Verification.xlsx ({len(df_log)} files scanned)")
    else:
        print("No chapters were found during the scan.")

    # Output 2: Duplicate Report
    if not duplicate_data:
        print("No duplicates found. Your libraries are clean!")
    else:
        df_dupe = pd.DataFrame(duplicate_data)
        df_dupe.to_excel("Duplicate_Chapters_Report.xlsx", index=False)
        print(f"Duplicate report generated: Duplicate_Chapters_Report.xlsx ({len(df_dupe)} duplicates found)")

if __name__ == "__main__":
    # Define your list of target directories to scan
    LIBRARY_PATHS = [
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
    ]
    
    # Margin of error allowed between the base chapter and the sum of the sub-chapters.
    PAGE_TOLERANCE = 5  

    print(f"Scanning {len(LIBRARY_PATHS)} library locations...")
    duplicates, scanned_log = find_duplicate_chapters(LIBRARY_PATHS, margin=PAGE_TOLERANCE)
    generate_reports(duplicates, scanned_log)
import os
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

# Register namespaces so ElementTree doesn't overwrite them with "ns0", "ns1", etc.
ET.register_namespace('xsd', "http://www.w3.org/2001/XMLSchema")
ET.register_namespace('xsi', "http://www.w3.org/2001/XMLSchema-instance")
ET.register_namespace('ty', "http://www.w3.org/2001/XMLSchema")
ET.register_namespace('mh', "http://www.w3.org/2001/XMLSchema")

def process_comicinfo(args):
    """
    Checks and updates the ComicInfo.xml inside a CBZ archive.
    Returns a tuple: (log_string, console_message)
    """
    # Unpack arguments
    file_path, folder_name, cbz_count, dry_run = args
    filename_no_ext = os.path.splitext(os.path.basename(file_path))[0]
    
    has_xml = False
    needs_update = False
    
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            if 'ComicInfo.xml' in zf.namelist():
                has_xml = True
                xml_data = zf.read('ComicInfo.xml')
                root = ET.fromstring(xml_data)
            else:
                root = ET.Element('ComicInfo', {
                    'xmlns:xsd': 'http://www.w3.org/2001/XMLSchema',
                    'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance'
                })
    except zipfile.BadZipFile:
        return None, f"[-] Skipping corrupted or invalid archive: {os.path.basename(file_path)}"
    except Exception as e:
        return None, f"[-] Error reading {os.path.basename(file_path)}: {e}"

    def get_or_create_element(parent, tag):
        elem = parent.find(tag)
        if elem is None:
            elem = ET.SubElement(parent, tag)
        return elem

    title_elem = get_or_create_element(root, 'Title')
    series_elem = get_or_create_element(root, 'Series')
    
    current_title = title_elem.text if title_elem.text else ""
    current_series = series_elem.text if series_elem.text else ""

    # Set default targets to current values
    target_title = current_title
    target_series = current_series

    # 1. Apply the Logic Rules (Case-insensitive 'chapter' and 'volume' check)
    if has_xml:
        title_lower = current_title.lower()
        if "chapter" in title_lower or "volume" in title_lower:
            if cbz_count == 1:
                target_title = current_series
            else:
                target_title = f"{current_series} - {filename_no_ext}".strip()
    else:
        target_series = folder_name
        if cbz_count == 1:
            target_title = folder_name
        else:
            target_title = f"{folder_name} - {filename_no_ext}".strip()

    # 2. Check if changes are ACTUALLY required
    if target_title != current_title or target_series != current_series:
        needs_update = True
        title_elem.text = target_title
        series_elem.text = target_series

    # Generate log entry and optionally save changes
    if needs_update:
        status_tag = "[DRY RUN] Would update:" if dry_run else "[+] Updated:"
        console_msg = f"{status_tag} {os.path.basename(file_path)}"
        
        if not dry_run:
            try:
                update_archive(file_path, root)
            except Exception as e:
                return None, f"[-] Failed to write {os.path.basename(file_path)}: {e}"
        
        # Create a detailed log string for the report (Re-formatted for clarity)
        log_entry = (
            f"Path:       {file_path}\n"
            f"Old Title:  {current_title if current_title else '<None>'}\n"
            f"New Title:  {target_title}\n"
            f"Old Series: {current_series if current_series else '<None>'}\n"
            f"New Series: {target_series}\n"
            f"{'=' * 60}"
        )
        return log_entry, console_msg
        
    return None, None


def update_archive(original_path, xml_root):
    """
    Safely modifies the zip archive. Uses the original file's compression 
    types to avoid unnecessarily re-compressing JPEGs/PNGs.
    """
    fd, temp_path = tempfile.mkstemp(suffix='.cbz')
    os.close(fd) 
    
    xml_str = ET.tostring(xml_root, encoding='utf-8', xml_declaration=True).decode('utf-8')
    
    with zipfile.ZipFile(original_path, 'r') as zin:
        with zipfile.ZipFile(temp_path, 'w') as zout:
            for item in zin.infolist():
                if item.filename != 'ComicInfo.xml':
                    zout.writestr(item, zin.read(item.filename))
            
            new_xml_info = zipfile.ZipInfo('ComicInfo.xml')
            new_xml_info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(new_xml_info, xml_str)
            
    shutil.move(temp_path, original_path)


def scan_directory_parallel(base_dir, dry_run=False):
    """
    Traverses the directory, collects tasks, and processes them concurrently.
    Filters out duplicate files reported by network/virtual drives.
    """
    tasks = []
    seen_paths = set() # Memory bank to stop duplicates
    
    print("Scanning folders to build task list...")
    for root_dir, _, files in os.walk(base_dir):
        cbz_files = [f for f in files if f.lower().endswith('.cbz')]
        if not cbz_files:
            continue
            
        cbz_count = len(cbz_files)
        folder_name = os.path.basename(root_dir)
        
        for cbz in cbz_files:
            # Get the absolute path to ensure accurate deduplication
            full_path = os.path.abspath(os.path.join(root_dir, cbz))
            
            # --- DEDUPLICATOR ---
            # If the OS stutters and gives us the exact same file twice, ignore it.
            if full_path in seen_paths:
                continue
                
            seen_paths.add(full_path)
            tasks.append((full_path, folder_name, cbz_count, dry_run))
            
    total_tasks = len(tasks)
    print(f"Found {total_tasks} unique CBZ files. Starting parallel processing...\n")

    update_logs = []
    processed_count = 0
    
    max_threads = max(1, multiprocessing.cpu_count() - 2)

    with ProcessPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process_comicinfo, task): task for task in tasks}
        
        for future in as_completed(futures):
            processed_count += 1
            try:
                log_entry, console_msg = future.result()
                if console_msg:
                    print(f"[{processed_count}/{total_tasks}] {console_msg}")
                elif processed_count % 100 == 0 or processed_count == total_tasks:
                    print(f"[{processed_count}/{total_tasks}] Checking files...", end='\r')
                    
                if log_entry:
                    update_logs.append(log_entry)
                    
            except Exception as exc:
                print(f"\n[{processed_count}/{total_tasks}] Fatal error on a worker process: {exc}")
                
    return update_logs


if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    print("=== CBZ ComicInfo MULTI-CORE Auto-Formatter ===")
    
    target_directory = r"Z:\Manga CBZ\Doujinshi\NewFolder"
    print(f"Target Directory set to: {target_directory}\n")
        
    if os.path.isdir(target_directory):
        user_input = input("Enable Dry Run mode? (Type 'y' to generate a report ONLY, or 'n' to apply changes): ").strip().lower()
        is_dry_run = user_input == 'y' or user_input == 'yes'
        
        if is_dry_run:
            print("\n--- DRY RUN INITIATED: No files will be modified ---")
        else:
            print("\n--- LIVE RUN INITIATED: Files will be modified ---")
            
        logs = scan_directory_parallel(target_directory, dry_run=is_dry_run)
        
        print("\n\nFinished processing!")
        
        if logs:
            report_name = "cbz_dry_run_report.txt" if is_dry_run else "cbz_update_report.txt"
            script_dir = os.path.dirname(os.path.abspath(__file__))
            report_path = os.path.join(script_dir, report_name)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(report_path, "w", encoding="utf-8") as report_file:
                if is_dry_run:
                    report_file.write(f"=== CBZ DRY RUN REPORT (NO FILES MODIFIED) ===\n")
                else:
                    report_file.write(f"=== CBZ UPDATE REPORT ===\n")
                    
                report_file.write(f"Generated on: {timestamp}\n")
                report_file.write(f"Total Files Flagged: {len(logs)}\n")
                report_file.write(f"=========================\n\n")
                report_file.write("\n".join(logs))
                
            print(f"Total files flagged for update: {len(logs)}")
            print(f"Report successfully saved to: {report_path}")
        else:
            print("No files required updating. All CBZ metadata is already perfect!")
    else:
        print(f"\nError: The path '{target_directory}' is not a valid directory. Please check if the drive is mounted or the folder exists.")
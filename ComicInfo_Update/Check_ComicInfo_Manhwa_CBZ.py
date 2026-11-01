import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from datetime import datetime
import zipfile

# Ensure shared configuration is available
_PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from shared.config import resolve_paths, get_reports_dir, is_dry_run_requested

def normalize_series_names(base_directories, report_filename="normalization_report_manhwa.txt", dry_run=True):
    """
    Scans manga library directories for .cbz files, unifies the <Series> tag 
    in their ComicInfo.xml to the most commonly used name, and generates a text report. 
    Can be run in a 'dry run' mode to preview changes without modifying files.
    """
    
    # Register namespaces commonly found in Mihon/Tachiyomi metadata
    namespaces = {
        'xsd': "http://www.w3.org/2001/XMLSchema",
        'xsi': "http://www.w3.org/2001/XMLSchema-instance",
        'ty': "http://www.w3.org/2001/XMLSchema",
        'mh': "http://www.w3.org/2001/XMLSchema"
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    report_lines = []
    total_files_changed = 0

    # Record the start time and run mode for the report header
    report_lines.append(f"--- Manga Series Normalization Report ---")
    report_lines.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    mode_text = "DRY RUN (No files were modified)" if dry_run else "LIVE RUN (Files were updated)"
    report_lines.append(f"Mode: {mode_text}\n")
    
    print(f"Starting script in {mode_text.upper()} mode...")

    for base_directory in base_directories:
        base_path = Path(base_directory)
        print(f"\n--- Scanning base directory: {base_path} ---")
        
        if not base_path.exists() or not base_path.is_dir():
            print(f"Warning: Directory not found or invalid: {base_path}. Skipping.")
            continue

        for series_folder in base_path.iterdir():
            if not series_folder.is_dir():
                continue

            # Look for CBZ files instead of bare XML files
            cbz_files = list(series_folder.rglob("*.cbz"))
            if not cbz_files:
                continue

            series_names = []
            parsed_data = []

            # Parse XMLs inside the CBZs and collect current <Series> values
            for cbz_file in cbz_files:
                try:
                    with zipfile.ZipFile(cbz_file, 'r') as zf:
                        # Check if ComicInfo.xml exists in the archive
                        if "ComicInfo.xml" in zf.namelist():
                            with zf.open("ComicInfo.xml") as xml_file:
                                tree = ET.parse(xml_file)
                                root = tree.getroot()
                                series_elem = root.find("Series")
                                
                                if series_elem is not None and series_elem.text:
                                    series_names.append(series_elem.text)
                                    parsed_data.append((cbz_file, root, series_elem, series_elem.text))
                except zipfile.BadZipFile:
                    print(f"Warning: Corrupted or invalid ZIP/CBZ file: {cbz_file}")
                except ET.ParseError as e:
                    print(f"Error parsing XML for {cbz_file}: {e}")
                except Exception as e:
                    print(f"Unexpected error reading {cbz_file}: {e}")
            
            if not series_names:
                continue

            # Determine the most common <Series> name
            most_common_series = Counter(series_names).most_common(1)[0][0]
            
            # Update files that do not match the most common name
            folder_updates = 0
            folder_report_lines = []
            
            for cbz_file, root, series_elem, current_name in parsed_data:
                if current_name != most_common_series:
                    
                    # Only apply and save the changes if we are NOT in a dry run
                    if not dry_run:
                        series_elem.text = most_common_series
                        
                        # Generate bytes for the updated XML
                        xml_bytes = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
                        
                        temp_cbz = cbz_file.with_name(cbz_file.name + '.tmp')
                        
                        try:
                            # Rebuild the CBZ file with the modified XML
                            with zipfile.ZipFile(cbz_file, 'r') as zin:
                                with zipfile.ZipFile(temp_cbz, 'w') as zout:
                                    for item in zin.infolist():
                                        if item.filename == "ComicInfo.xml":
                                            zout.writestr(item, xml_bytes)
                                        else:
                                            zout.writestr(item, zin.read(item.filename))
                            
                            # Replace the old file with the new one
                            temp_cbz.replace(cbz_file)
                        except Exception as e:
                            print(f"Failed to update {cbz_file}: {e}")
                            if temp_cbz.exists():
                                temp_cbz.unlink()
                            continue
                    
                    # Log the specific change (adjusting wording based on mode)
                    action_word = "Would change" if dry_run else "Changed"
                    folder_report_lines.append(f"  - {cbz_file.name}")
                    folder_report_lines.append(f"    {action_word} from: '{current_name}' -> '{most_common_series}'")
                    
                    folder_updates += 1
                    total_files_changed += 1
            
            # If changes were identified in this series folder, add them to the main report
            if folder_updates > 0:
                report_lines.append(f"[{series_folder.name}]")
                report_lines.append(f"Target Series Name: '{most_common_series}'")
                report_lines.extend(folder_report_lines)
                report_lines.append(f"Folder changes: {folder_updates}\n")
                
                status_word = "Would unify" if dry_run else "Unified"
                print(f"[{series_folder.name}] {status_word} {folder_updates} files.")
            else:
                print(f"[{series_folder.name}] All {len(cbz_files)} files already match.")

    # Finalize report with totals
    report_lines.append("-" * 40)
    summary_word = "Total Files That Would Be Changed" if dry_run else "Total Files Changed"
    report_lines.append(f"{summary_word}: {total_files_changed}")

    # Write the report to a text file
    if total_files_changed > 0:
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        print(f"\n✅ Processing complete. Report saved to: {report_filename}")
        print(f"{summary_word}: {total_files_changed}")
    else:
        print("\n✅ Processing complete. No files needed updating, so no report was generated.")

if __name__ == "__main__":
    target_directories = resolve_paths([
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
    
    report_file = str(get_reports_dir() / "normalization_report_manhwa.txt")
    is_dry = is_dry_run_requested(default=True)

    normalize_series_names(
        target_directories, 
        report_filename=report_file, 
        dry_run=is_dry
    )

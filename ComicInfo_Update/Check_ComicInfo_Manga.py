import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from datetime import datetime

def normalize_series_names(base_directories, report_filename="normalization_report.txt", dry_run=True):
    """
    Scans manga library directories, unifies the <Series> tag to the most commonly 
    used name, and generates a text report. Can be run in a 'dry run' mode to 
    preview changes without modifying files.
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

            xml_files = list(series_folder.rglob("ComicInfo.xml"))
            if not xml_files:
                continue

            series_names = []
            parsed_data = []

            # Parse XMLs and collect current <Series> values
            for xml_file in xml_files:
                try:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()
                    series_elem = root.find("Series")
                    
                    if series_elem is not None and series_elem.text:
                        series_names.append(series_elem.text)
                        parsed_data.append((xml_file, tree, series_elem, series_elem.text))
                except ET.ParseError as e:
                    print(f"Error parsing XML for {xml_file}: {e}")
            
            if not series_names:
                continue

            # Determine the most common <Series> name
            most_common_series = Counter(series_names).most_common(1)[0][0]
            
            # Update files that do not match the most common name
            folder_updates = 0
            folder_report_lines = []
            
            for xml_file, tree, series_elem, current_name in parsed_data:
                if current_name != most_common_series:
                    
                    # Only apply and save the changes if we are NOT in a dry run
                    if not dry_run:
                        series_elem.text = most_common_series
                        tree.write(xml_file, encoding="UTF-8", xml_declaration=True)
                    
                    # Log the specific change (adjusting wording based on mode)
                    action_word = "Would change" if dry_run else "Changed"
                    folder_report_lines.append(f"  - {xml_file.name} in '{xml_file.parent.name}'")
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
                print(f"[{series_folder.name}] All {len(xml_files)} files already match.")

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
    # Define your list of target directories here
    target_directories = [
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
    
    # Set dry_run to True to safely test. Set to False to actually modify the files.
    # normalize_series_names(
    #     target_directories, 
    #     report_filename="normalization_report.txt", 
    #     dry_run=True  
    # )

    normalize_series_names(
        target_directories, 
        report_filename="normalization_report.txt", 
        dry_run=False  
    )
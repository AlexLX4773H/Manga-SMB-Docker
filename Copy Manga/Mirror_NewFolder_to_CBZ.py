import os
import zipfile
import time
import tempfile
import shutil

def sync_source_to_cbz_mirror(source_dir, dest_dir):
    # Standardize paths for the OS and remove trailing slashes
    source_dir = os.path.normpath(source_dir)
    dest_dir = os.path.normpath(dest_dir)

    # Supported image extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
    
    if not os.path.exists(source_dir):
        print(f"CRITICAL ERROR: Source directory not found: {source_dir}")
        return

    print(f"--- 1. Scanning Source: {source_dir} ---")
    source_leaves = {} # Maps relative path -> dict of {root, files}
    
    for root, dirs, files in os.walk(source_dir):
        # If 'dirs' is empty, this is a leaf folder
        if not dirs:
            has_images = any(os.path.splitext(f)[1].lower() in image_extensions for f in files)
            if has_images:
                rel_path = os.path.relpath(root, source_dir)
                # Save the file list so we don't have to scan the disk again later
                source_leaves[rel_path] = {'root': root, 'files': files}

    print(f"Found {len(source_leaves)} valid image folders in source.\n")
    
    print(f"--- 2. Scanning Destination: {dest_dir} ---")
    dest_cbzs = {} # Maps relative path (without .cbz) -> full destination cbz path
    
    if not os.path.exists(dest_dir):
        print("Destination does not exist. Creating it...")
        os.makedirs(dest_dir)
        
    for root, dirs, files in os.walk(dest_dir):
        for file in files:
            if file.lower().endswith('.cbz'):
                full_cbz_path = os.path.join(root, file)
                rel_cbz_dir = os.path.relpath(root, dest_dir)
                cbz_name_no_ext = os.path.splitext(file)[0]
                
                if rel_cbz_dir == '.':
                    rel_path = cbz_name_no_ext
                else:
                    rel_path = os.path.join(rel_cbz_dir, cbz_name_no_ext)
                    
                dest_cbzs[rel_path] = full_cbz_path

    print(f"Found {len(dest_cbzs)} existing .cbz files in destination.\n")

    print("--- 3. Syncing: Archiving New Folders ---")
    new_count = 0
    for rel_path, src_data in source_leaves.items():
        if rel_path not in dest_cbzs:
            dest_cbz_full_path = os.path.join(dest_dir, rel_path + '.cbz')
            dest_cbz_dir = os.path.dirname(dest_cbz_full_path)
            
            # Ensure the mirror directory structure exists on the mapped drive
            os.makedirs(dest_cbz_dir, exist_ok=True)
            
            print(f"Archiving new: '{rel_path}.cbz'...")
            start_time = time.time()
            success = False
            
            # Create a local temporary file to build the zip safely
            fd, local_temp_zip = tempfile.mkstemp(suffix=".cbz")
            os.close(fd) 
            
            try:
                # 1. Build the zip locally
                src_full_path = src_data['root']
                src_files = src_data['files']
                
                with zipfile.ZipFile(local_temp_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in src_files:
                        source_file_path = os.path.join(src_full_path, file)
                        # Add to archive directly from mapped drive
                        zipf.write(source_file_path, arcname=file)
                
                local_zip_size = os.path.getsize(local_temp_zip)
                
                # 2. Copy the completed zip to the final destination
                shutil.copy2(local_temp_zip, dest_cbz_full_path)
                
                # 3. Verify size
                remote_zip_size = os.path.getsize(dest_cbz_full_path)
                if remote_zip_size == local_zip_size and local_zip_size > 0:
                    success = True
                else:
                    print(f"  -> VERIFICATION FAILED: Size mismatch!")
                    
            except Exception as e:
                print(f"  -> Error: {e}")
                
            finally:
                if not success:
                    try:
                        if os.path.exists(dest_cbz_full_path):
                            os.remove(dest_cbz_full_path)
                    except Exception:
                        pass
                if os.path.exists(local_temp_zip):
                    os.remove(local_temp_zip)

            if success:
                duration = time.time() - start_time
                print(f"  -> Created in {duration:.2f}s")
                new_count += 1

    if new_count == 0:
        print("No new folders to archive.")

    print("\n--- 4. Syncing: Removing Orphaned CBZ Files ---")
    removed_count = 0
    for rel_path, dest_full_path in dest_cbzs.items():
        if rel_path not in source_leaves:
            print(f"Removing orphaned archive: '{rel_path}.cbz'")
            try:
                os.remove(dest_full_path)
                removed_count += 1
            except Exception as e:
                print(f"  -> Failed to remove {dest_full_path}. Error: {e}")

    if removed_count == 0:
        print("No orphaned files to remove.")
        
    print("\n--- 5. Cleaning up empty mirror directories ---")
    # Walk bottom-up to safely delete empty nested directories
    for root, dirs, files in os.walk(dest_dir, topdown=False):
        try:
            # If the folder has no contents, delete it
            if not os.listdir(root):
                os.rmdir(root)
                print(f"Removed empty directory: {root}")
        except Exception:
            pass

if __name__ == "__main__":
    
    # --- Target Paths mapped to Z: ---
    # Put the path where your original unpacked image folders are
    SOURCE_DIR = r"Z:\Backup2\Vere\NewFolder"
    # SOURCE_DIR = r"Z:\Manga"
    
    # Put the path where you want the mirrored .cbz structure to be generated
    DEST_DIR = r"Z:\Manga CBZ\Doujinshi\NewFolder"
    # DEST_DIR = r"Z:\Manga CBZ\Manga"

    print(f"SOURCE:      {SOURCE_DIR}")
    print(f"DESTINATION: {DEST_DIR}")
    print("WARNING: This script will create new CBZs and DELETE any CBZs in the destination that no longer exist in the source.")
    
    confirm = input("Proceed with synchronization? (y/n): ")
    
    if confirm.lower() == 'y':
        total_start = time.time()
        sync_source_to_cbz_mirror(SOURCE_DIR, DEST_DIR)
        total_duration = time.time() - total_start
        print(f"\nMirror synchronization complete in {total_duration:.2f} seconds.")
    else:
        print("\nOperation cancelled.")
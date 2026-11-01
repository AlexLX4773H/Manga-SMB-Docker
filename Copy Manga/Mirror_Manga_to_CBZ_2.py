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

    print(f"\n--- 1. Scanning Source: {source_dir} ---")
    source_leaves = {} # Maps relative path -> dict of {root, files}
    source_cbzs = {}   # Maps relative path (without .cbz) -> full source cbz path
    
    for root, dirs, files in os.walk(source_dir):
        # 1a. Check for leaf folders containing images
        if not dirs:
            has_images = any(os.path.splitext(f)[1].lower() in image_extensions for f in files)
            if has_images:
                rel_path = os.path.relpath(root, source_dir)
                source_leaves[rel_path] = {'root': root, 'files': files}

        # 1b. Check for already existing .cbz files in the source
        for file in files:
            if file.lower().endswith('.cbz'):
                full_cbz_path = os.path.join(root, file)
                rel_cbz_dir = os.path.relpath(root, source_dir)
                cbz_name_no_ext = os.path.splitext(file)[0]
                
                if rel_cbz_dir == '.':
                    rel_path = cbz_name_no_ext
                else:
                    rel_path = os.path.join(rel_cbz_dir, cbz_name_no_ext)
                    
                source_cbzs[rel_path] = full_cbz_path

    print(f"Found {len(source_leaves)} valid image folders in source.")
    print(f"Found {len(source_cbzs)} existing .cbz files in source.\n")
    
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

    print("\n--- 3.5. Syncing: Copying Source CBZ Files ---")
    copied_count = 0
    for rel_path, src_full_path in source_cbzs.items():
        if rel_path not in dest_cbzs:
            dest_cbz_full_path = os.path.join(dest_dir, rel_path + '.cbz')
            dest_cbz_dir = os.path.dirname(dest_cbz_full_path)
            
            os.makedirs(dest_cbz_dir, exist_ok=True)
            
            print(f"Copying existing source CBZ: '{rel_path}.cbz'...")
            start_time = time.time()
            try:
                shutil.copy2(src_full_path, dest_cbz_full_path)
                duration = time.time() - start_time
                print(f"  -> Copied in {duration:.2f}s")
                copied_count += 1
            except Exception as e:
                print(f"  -> Error copying {src_full_path}: {e}")
                
    if copied_count == 0:
        print("No new CBZ files to copy from source.")

    print("\n--- 4. Syncing: Removing Orphaned CBZ Files ---")
    removed_count = 0
    for rel_path, dest_full_path in dest_cbzs.items():
        # Only remove if the .cbz wasn't built from an image folder AND doesn't exist as a .cbz in the source
        if rel_path not in source_leaves and rel_path not in source_cbzs:
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
    # Define as many source/destination pairs as you need in this list.
    # Format: (r"SOURCE_PATH", r"DESTINATION_PATH")
    SYNC_PAIRS = [
        (r"Z:\Manga\Manga_1", r"Z:\Manga CBZ\Manga\Manga_1"),
        (r"Z:\Manga\Manga_A2", r"Z:\Manga CBZ\Manga\Manga_A2"),
        # (r"Z:\Another\Source", r"Z:\Another\Destination"),
    ]

    print("=== CBZ MIRROR SYNC ===")
    print("Configured pairs to synchronize:")
    for i, (src, dest) in enumerate(SYNC_PAIRS, 1):
        print(f"  {i}. SOURCE: {src}")
        print(f"     DEST:   {dest}")
        
    print("\nWARNING: This script will create/copy new CBZs and DELETE any CBZs in the destinations that no longer exist in the sources.")
    
    confirm = input("\nProceed with synchronization for all pairs? (y/n): ")
    
    if confirm.lower() == 'y':
        total_start = time.time()
        
        # Loop through each pair and run the sync
        for i, (src, dest) in enumerate(SYNC_PAIRS, 1):
            print(f"\n=======================================================")
            print(f"Processing Pair {i}/{len(SYNC_PAIRS)}")
            print(f"=======================================================")
            sync_source_to_cbz_mirror(src, dest)
            
        total_duration = time.time() - total_start
        print(f"\n=======================================================")
        print(f"All operations complete in {total_duration:.2f} seconds.")
    else:
        print("\nOperation cancelled.")
import os
import zipfile
import time
import tempfile
import shutil

def convert_leaf_folders_to_cbz(target_paths):
    # Supported image extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
    
    # Iterate through the provided list of paths
    for base_path in target_paths:
        # Standardize path slashes
        base_path = os.path.normpath(base_path)
        
        if not os.path.exists(base_path):
            print(f"Warning: Path does not exist or is inaccessible, skipping: {base_path}")
            continue
            
        print(f"--- Scanning base path: {base_path} ---")
        
        # Use topdown=False so we process children before parents
        for root, dirs, files in os.walk(base_path, topdown=False):
            
            # If 'dirs' is empty, this is a leaf folder
            if not dirs:
                # Check if the folder contains any images
                has_images = any(os.path.splitext(f)[1].lower() in image_extensions for f in files)
                
                if has_images:
                    folder_name = os.path.basename(root)
                    parent_dir = os.path.dirname(root)
                    
                    # Define the output path for the CBZ file
                    cbz_filename = f"{folder_name}.cbz"
                    final_cbz_path = os.path.join(parent_dir, cbz_filename)
                    
                    # Check if archive already exists
                    if os.path.exists(final_cbz_path):
                        print(f"Skipping (CBZ already exists): {final_cbz_path}")
                        continue

                    print(f"Archiving: '{root}'...")
                    
                    start_time = time.time()
                    success = False
                    
                    # Create a local temporary file to build the zip safely before transferring
                    fd, local_temp_zip = tempfile.mkstemp(suffix=".cbz")
                    os.close(fd) 
                    
                    try:
                        # 1. Build the zip locally in the temp directory
                        with zipfile.ZipFile(local_temp_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for file in files:
                                source_file_path = os.path.join(root, file)
                                # Write the file to the archive, using just the filename as the archive path
                                zipf.write(source_file_path, arcname=file)
                        
                        # Calculate exactly how big the file should be
                        local_zip_size = os.path.getsize(local_temp_zip)
                        
                        # 2. Copy the completed zip to the final mapped drive location
                        shutil.copy2(local_temp_zip, final_cbz_path)
                        
                        # 3. STRICT VERIFICATION
                        # Ask the OS for the exact size of the newly placed file
                        final_zip_size = os.path.getsize(final_cbz_path)
                        
                        if final_zip_size == local_zip_size and local_zip_size > 0:
                            success = True
                            print(f"  -> Verification passed: Final size ({final_zip_size} bytes) perfectly matches local build.")
                        else:
                            print(f"  -> VERIFICATION FAILED: Size mismatch! Local: {local_zip_size}, Final: {final_zip_size}")
                            
                    except Exception as e:
                        print(f"  -> Error during creation/transfer: {e}")
                        
                    finally:
                        # If verification failed or an error occurred, attempt to clean up the broken final file
                        if not success:
                            try:
                                if os.path.exists(final_cbz_path):
                                    os.remove(final_cbz_path)
                                    print(f"  -> Cleaned up incomplete file: {cbz_filename}")
                            except Exception:
                                pass
                                
                        # Always clean up the local temp file
                        if os.path.exists(local_temp_zip):
                            os.remove(local_temp_zip)

                    end_time = time.time()
                    duration = end_time - start_time

                    # 4. ONLY delete the original leaf folder if the strict verification passed
                    if success:
                        try:
                            shutil.rmtree(root)
                            print(f"Success: Created '{final_cbz_path}' in {duration:.2f}s and safely deleted original folder.\n")
                        except Exception as e:
                            print(f"Warning: Verified CBZ in {duration:.2f}s, but failed to delete original folder '{root}'. Error: {e}\n")
                    else:
                        print(f"Aborted: Folder '{root}' was NOT deleted due to verification failure.\n")


if __name__ == "__main__":
    
    # --- Target Paths mapped to Z: ---
    # Adjust this path based on exactly how deep you mapped the Z: drive.
    library_paths = [
        r"Z:\Manga CBZ\Manga"
    ]
    
    print("WARNING: This script verifies .cbz creations by byte-size, and DELETES original folders.")
    confirm = input("Proceed? (y/n): ")
    
    if confirm.lower() == 'y':
        total_start_time = time.time()
        
        convert_leaf_folders_to_cbz(library_paths)
        
        total_end_time = time.time()
        total_duration = total_end_time - total_start_time
        print(f"\nFinished processing all paths in {total_duration:.2f} seconds.")
    else:
        print("\nOperation cancelled.")
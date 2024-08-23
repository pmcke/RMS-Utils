
"""
extractBz2.py Extracts all the bz2 archives in a folder.
Usage python - 
"""
import sys
import bz2
import os
import tarfile


def extract_bz2_files(folder_path):
    # Ensure the provided folder path exists
    if not os.path.exists(folder_path):
        print(f"The folder path {folder_path} does not exist.")
        return

    # List all files in the provided folder
    files = os.listdir(folder_path)

    # Process each file in the folder
    for file_name in files:
        # Check if the file has a .tar.bz2 extension
        if file_name.endswith('.tar.bz2'):
            # Create the full file path
            file_path = os.path.join(folder_path, file_name)
            try:
                # Open the .tar.bz2 file
                with tarfile.open(file_path, 'r:bz2') as tar:
                    # Extract all contents of the tar.bz2 file
                    tar.extractall(path=folder_path)

                print(f"Extracted {file_name}")
            except Exception as e:
                print(f"Failed to extract {file_name}: {e}")


# Example usage:
# Replace with the path to your folder containing .tar.bz2 files
folder_path = sys.argv[1]
# folder_path = 'path/to/your/folder'
extract_bz2_files(folder_path)

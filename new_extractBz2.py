"""
extractBz2.py
Extracts all the .tar.bz2 archives in a folder.

Usage:
    python extractBz2.py <input_folder> [output_folder]

If output_folder is not provided, files will be extracted into the input folder.
Extraction preserves only the last folder level from the tar archive path.
"""

import sys
import os
import tarfile


def extract_bz2_files(input_folder, output_folder=None):
    # Ensure the provided input folder path exists
    if not os.path.exists(input_folder):
        print(f"The folder path {input_folder} does not exist.")
        return

    # Default output folder to input folder if not provided
    if output_folder is None:
        output_folder = input_folder

    # Create output folder if it does not exist
    os.makedirs(output_folder, exist_ok=True)

    # List all files in the provided folder
    files = os.listdir(input_folder)

    # Process each file in the folder
    for file_name in files:
        if file_name.endswith('.tar.bz2'):
            file_path = os.path.join(input_folder, file_name)
            try:
                with tarfile.open(file_path, 'r:bz2') as tar:
                    for member in tar.getmembers():
                        if member.isfile():  # only extract files, skip empty dirs
                            parts = member.name.strip("/").split("/")

                            if len(parts) > 1:
                                new_name = os.path.join(parts[-2], parts[-1])
                            else:
                                new_name = parts[-1]

                            # Override member path
                            member.name = new_name
                            tar.extract(member, path=output_folder)

                print(f"Extracted {file_name} to {output_folder}")
            except Exception as e:
                print(f"Failed to extract {file_name}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extractBz2.py <input_folder> [output_folder]")
    else:
        input_folder = sys.argv[1]
        output_folder = sys.argv[2] if len(sys.argv) > 2 else None
        extract_bz2_files(input_folder, output_folder)

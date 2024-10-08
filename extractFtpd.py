"""
Extracts files with the pattern *FTPdetectinfo*.* and *platepars_all*.* from bz2 files in the path
Places the resulting files in a folder named after the first 6 characteers of the archive name.
99% of this is written by ChatGPT
"""

import bz2
import tarfile
import os
import fnmatch
import sys

def extract_files_from_bz2(bz2_file_path, target_file_pattern):
    try:
        # Create a subdirectory named using the first 6 characters of the archive name
        archive_name = os.path.basename(bz2_file_path)
        subdirectory_name = archive_name[:6]
        subdirectory_path = os.path.join(os.path.dirname(bz2_file_path), subdirectory_name)

        # Create the subdirectory if it doesn't exist
        os.makedirs(subdirectory_path, exist_ok=True)

        with bz2.BZ2File(bz2_file_path, 'rb') as file:
            # Check if it's a tar archive
            tar_magic_number = b'ustar'  # tar files contain 'ustar' at byte 257-262
            # Read more than enough to cover the first tar header block
            file_start = file.read(1024)

            if tar_magic_number in file_start:
                # Reset file pointer and open as tar archive
                file.seek(0)
                with tarfile.open(fileobj=bz2.BZ2File(bz2_file_path, 'rb')) as tar:
                    for member in tar.getmembers():
                        if fnmatch.fnmatch(member.name, target_file_pattern):
                            tar.extract(member, path=subdirectory_path)
                            print(f"Extracted {member.name} to {subdirectory_path}")
                    else:
                        print(f"No files matching pattern '{target_file_pattern}' found in the tar archive {bz2_file_path}.")
            else:
                # If it's not a tar archive, extract the single file
                file.seek(0)  # Reset file pointer
                output_file_name = os.path.join(subdirectory_path, target_file_pattern)
                with open(output_file_name, 'wb') as output_file:
                    output_file.write(file.read())
                print(f"Extracted {output_file_name} to {subdirectory_path}")
    except Exception as e:
        print(f"An error occurred while processing {bz2_file_path}: {e}")

def extract_from_all_bz2_files(folder_path, target_file_pattern):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.bz2'):
                bz2_file_path = os.path.join(root, file)
                extract_files_from_bz2(bz2_file_path, target_file_pattern)

# Example usage
folder_path = sys.argv[1]
target_file_pattern1 = '*FTPdetectinfo*.*'
target_file_pattern2 = '*platepars_all*.*'
extract_from_all_bz2_files(folder_path, target_file_pattern1)
extract_from_all_bz2_files(folder_path, target_file_pattern2)

"""
extract_captured_stack.py Created pretty exclusively by ChatGPT.
Extracts all files with the pattern "*captured_stack.jpg" from any bz2 file in the path
Usage python -u extract_captured_stack.py <folder path>
"""

import bz2
import tarfile
import os
import fnmatch
import sys


def extract_file_from_bz2(bz2_file_path, target_file_pattern):
    try:
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
                            tar.extract(
                                member, path=os.path.dirname(bz2_file_path))
                            print(f"Extracted {member.name} from {bz2_file_path}")
                            return
                    print(f"No file matching pattern '{target_file_pattern}' found in the tar archive {bz2_file_path}.")
            else:
                # If it's not a tar archive, extract the single file
                file.seek(0)  # Reset file pointer
                output_file_name = os.path.join(
                    os.path.dirname(bz2_file_path), target_file_pattern)
                with open(output_file_name, 'wb') as output_file:
                    output_file.write(file.read())
                print(f"Extracted {output_file_name} from {bz2_file_path}")
    except Exception as e:
        print(f"An error occurred while processing {bz2_file_path}: {e}")


def extract_from_all_bz2_files(folder_path, target_file_pattern):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.bz2'):
                bz2_file_path = os.path.join(root, file)
                extract_file_from_bz2(bz2_file_path, target_file_pattern)


# Example usage
folder_path = sys.argv[1]
# folder_path = r'D:\Libraries\OneDrive\Documents\Peter\Global_Meteor_Network\Events2\Original\20240621_073515'
target_file_pattern1 = '*FTPdetectinfo*.*'
target_file_pattern2 = '*platepars_all*.*'
extract_from_all_bz2_files(folder_path, target_file_pattern1)
extract_from_all_bz2_files(folder_path, target_file_pattern2)

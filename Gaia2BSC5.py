""" 
Usage python gaia2Bsc55.py <directory_path>
Writen by Peter McKellar with help from Chat GPT
This looks for .config files in a directory and below, then changes the star_catalog line from gaia to BSC5
"""

import os
import sys


def changeline(config_file):
    if os.path.isfile(config_file):
        try:
            with open(config_file, "r+") as f:
                lines = f.readlines()
                f.seek(0)  # Move the file pointer to the beginning of the file
                found = False  # Variable to track if the line is found
                for line in lines:
                    if line.strip()[0:10] == 'stationID:':  # Get station ID
                        stationID = line.strip()[-6:]

                    if line.strip() == 'star_catalog_file: gaia_dr2_mag_11.5.npy':
                        line = 'star_catalog_file: BSC5\n'  # Modify the line
                        found = True  # Line is found
                        print("Line Changed ", stationID)
                    f.write(line)  # Write the line back to the file

                f.truncate()  # Truncate the file if it was shortened

                if not found:
                    print("Line not found ", stationID)
        except FileNotFoundError:
            print("The '.config' file was not found.")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
    else:
        print(f"File not found: {config_file}")


if len(sys.argv) < 2:
    print("Usage: python gaia2Bsc5.py <directory_path>")
    sys.exit(1)

dir_path = sys.argv[1]

subdirs = [x[0] for x in os.walk(dir_path)]

for subdir in subdirs:
    config_file_path = os.path.join(subdir, ".config")
    if os.path.isfile(config_file_path):
        changeline(config_file_path)

import os
import datetime
import subprocess
from glob import glob

# Configuration
LOCAL_DIR = "/home/fireballslux/radiometer_data"
REMOTE_USER = "fireballs360"
REMOTE_HOST = "192.168.6.100"
REMOTE_DIR = "/home/fireballs360/Lux_download"
STATION_NAME = "NZ005A"

# Get yesterday's date
yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y%m%d')
pattern = f"*{yesterday}*"

# Find matching files
files_to_copy = glob(os.path.join(LOCAL_DIR, pattern))

if not files_to_copy:
    print(f"No files found matching pattern: {pattern}")
else:
    for file_path in files_to_copy:
        filename = os.path.basename(file_path)
        remote_filename = f"{STATION_NAME}_{filename}"
        remote_path = f"{REMOTE_USER}@{REMOTE_HOST}:{os.path.join(REMOTE_DIR, remote_filename)}"
        
        print(f"Copying {file_path} to {remote_path}")
        
        try:
            subprocess.run(["scp", file_path, remote_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to copy {filename}: {e}")

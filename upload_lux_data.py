#!/usr/bin/env python3

import bz2
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

STATION_NAME = "NZ005A"

# Pi Zero containing the lux/radiometer data
PI_HOST = "192.168.6.50"
PI_USER = "fireballslux"
PI_PASSWORD = "Fireb@llsLux360"
PI_DATA_DIR = "/home/fireballslux/radiometer_data"

# Local Ubuntu storage
LOCAL_DATA_DIR = Path.home() / "Lux_data_auto"

# GMN upload server
GMN_HOST = "gmn.uwo.ca"
GMN_USER = STATION_NAME.lower()
GMN_REMOTE_DIR = "/home/rmsuser/files/lux_data"

# IMPORTANT: SFTP uses the PRIVATE key, not id_rsa.pub
SSH_PRIVATE_KEY = Path.home() / ".ssh" / "id_rsa"


def run_command(command, description):
    """Run a command and stop if it fails."""
    try:
        subprocess.run(
            command,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: {description}")
        print(f"Command failed with return code {exc.returncode}")
        sys.exit(1)


def get_completed_utc_date():
    """
    Return yesterday's UTC date in YYYYMMDD format.

    Since this script is intended to run after a UTC day has completed,
    yesterday UTC is the date whose files we want.
    """
    now_utc = datetime.now(timezone.utc)
    completed_date = now_utc.date() - timedelta(days=1)
    return completed_date.strftime("%Y%m%d")


def download_files(date_string):
    """Download the four required CSV files from the Pi Zero."""

    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    filenames = [
        f"R_GAIN_LOW_{date_string}.csv",
        f"R_GAIN_MED_{date_string}.csv",
        f"R_GAIN_MAX_{date_string}.csv",
        f"R{date_string}.csv",
    ]

    downloaded_files = []

    print()
    print("Downloading files from Pi Zero")
    print("==============================")

    for filename in filenames:
        remote_file = f"{PI_DATA_DIR}/{filename}"

        # Prefix the downloaded filename with the station name
        local_filename = f"{STATION_NAME}_{filename}"
        local_file = LOCAL_DATA_DIR / local_filename

        print(f"{remote_file}")
        print(f"    -> {local_file}")

        command = [
            "sshpass",
            "-p",
            PI_PASSWORD,
            "scp",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{PI_USER}@{PI_HOST}:{remote_file}",
            str(local_file),
        ]

        run_command(
            command,
            f"Could not download {filename} from {PI_HOST}",
        )

        downloaded_files.append(local_file)

    return downloaded_files


def create_archive(files, date_string):
    """
    Create a tar archive compressed with bzip2.

    The filename is deliberately .bz2 as requested, although the contents
    are a tar+bzip2 archive containing multiple files.
    """

    archive_name = f"Lux_{STATION_NAME}_{date_string}.bz2"
    archive_path = LOCAL_DATA_DIR / archive_name

    print()
    print("Creating archive")
    print("================")
    print(archive_path)

    # tarfile supports bzip2 compression directly.
    with tarfile.open(archive_path, mode="w:bz2") as archive:
        for file_path in files:
            print(f"Adding {file_path.name}")
            archive.add(file_path, arcname=file_path.name)

    return archive_path


def upload_archive(archive_path):
    """Upload archive to GMN server using SFTP."""

    if not SSH_PRIVATE_KEY.exists():
        print()
        print(f"ERROR: SSH private key not found:")
        print(f"       {SSH_PRIVATE_KEY}")
        sys.exit(1)

    print()
    print("Uploading archive")
    print("=================")
    print(f"Server : {GMN_USER}@{GMN_HOST}")
    print(f"Remote : {GMN_REMOTE_DIR}/{archive_path.name}")

    # First ensure the remote lux_data directory exists.
    #
    # We use SSH for mkdir because SFTP itself does not provide a convenient
    # mkdir -p operation in batch mode.
    mkdir_command = [
        "ssh",
        "-i",
        str(SSH_PRIVATE_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{GMN_USER}@{GMN_HOST}",
        f"mkdir -p {shlex.quote(GMN_REMOTE_DIR)}",
    ]

    run_command(
        mkdir_command,
        f"Could not create {GMN_REMOTE_DIR} on {GMN_HOST}",
    )

    # Create a temporary SFTP batch file.
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        prefix="lux_sftp_",
        suffix=".txt",
    ) as batch:
        batch.write(f"cd {GMN_REMOTE_DIR}\n")
        batch.write(f'put "{archive_path}"\n')
        batch.write("quit\n")
        batch_filename = batch.name

    try:
        sftp_command = [
            "sftp",
            "-i",
            str(SSH_PRIVATE_KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-b",
            batch_filename,
            f"{GMN_USER}@{GMN_HOST}",
        ]

        run_command(
            sftp_command,
            f"Could not upload {archive_path.name} to {GMN_HOST}",
        )

    finally:
        try:
            os.unlink(batch_filename)
        except OSError:
            pass


def main():
    date_string = get_completed_utc_date()

    print("Lux Data Automatic Transfer")
    print("===========================")
    print(f"Station       : {STATION_NAME}")
    print(f"UTC date      : {date_string}")
    print(f"Local folder  : {LOCAL_DATA_DIR}")

    downloaded_files = download_files(date_string)

    print()
    print("All four files downloaded successfully.")

    archive_path = create_archive(downloaded_files, date_string)

    print()
    print(f"Archive created successfully: {archive_path}")

    upload_archive(archive_path)

    print()
    print("Transfer completed successfully.")
    print(f"Uploaded: {archive_path.name}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3

import json
import logging
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

STATION_NAME = "NZ005A"

# Pi Zero
PI_HOST = "192.168.6.50"
PI_USER = "fireballslux"
PI_PASSWORD = "Fireb@llsLux360"
PI_DATA_DIR = "/home/fireballslux/radiometer_data"

# Local Ubuntu storage
LOCAL_DATA_DIR = Path.home() / "Lux_data_auto"

# GMN server
GMN_HOST = "gmn.uwo.ca"
GMN_USER = STATION_NAME.lower()
GMN_REMOTE_DIR = "/home/rmsuser/files/lux_data"

# SSH private key for GMN SFTP
SSH_PRIVATE_KEY = Path.home() / ".ssh" / "id_rsa"

# Logging/state
LOG_FILE = LOCAL_DATA_DIR / "lux_transfer.log"
PENDING_FILE = LOCAL_DATA_DIR / "pending_dates.json"

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 60
CONNECT_TIMEOUT = 30


# ============================================================
# Logging
# ============================================================

def setup_logging():
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s UTC %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Force logging timestamps to UTC
    logging.Formatter.converter = time.gmtime


# ============================================================
# Pending-date management
# ============================================================

def load_pending_dates():
    if not PENDING_FILE.exists():
        return []

    try:
        with open(PENDING_FILE, "r") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

    except Exception as exc:
        logging.error("Could not read pending date file: %s", exc)

    return []


def save_pending_dates(dates):
    try:
        with open(PENDING_FILE, "w") as f:
            json.dump(sorted(set(dates)), f, indent=2)

    except Exception as exc:
        logging.error("Could not save pending date file: %s", exc)


def get_previous_utc_date():
    now_utc = datetime.now(timezone.utc)
    previous_date = now_utc.date() - timedelta(days=1)
    return previous_date.strftime("%Y%m%d")


# ============================================================
# Retry helper
# ============================================================

def wait_before_retry(attempt):
    if attempt < MAX_RETRIES:
        logging.info(
            "Waiting %d seconds before retry...",
            RETRY_DELAY_SECONDS,
        )
        time.sleep(RETRY_DELAY_SECONDS)


# ============================================================
# Check whether source file exists
# ============================================================

def remote_file_exists(filename):
    """
    Check whether a file exists on the Pi.

    Returns:
        True  = file exists
        False = file definitely does not exist
        None  = could not communicate with Pi
    """

    remote_path = f"{PI_DATA_DIR}/{filename}"

    remote_command = (
        f'if [ -f "{remote_path}" ]; '
        f'then echo EXISTS; '
        f'else echo MISSING; fi'
    )

    for attempt in range(1, MAX_RETRIES + 1):

        logging.info(
            "Checking for %s on Pi (attempt %d/%d)",
            filename,
            attempt,
            MAX_RETRIES,
        )

        command = [
            "sshpass",
            "-p",
            PI_PASSWORD,
            "ssh",
            "-o",
            f"ConnectTimeout={CONNECT_TIMEOUT}",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{PI_USER}@{PI_HOST}",
            remote_command,
        ]

        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=CONNECT_TIMEOUT + 10,
            )

            output = result.stdout.strip()

            if output == "EXISTS":
                return True

            if output == "MISSING":
                return False

            logging.warning(
                "Could not determine whether %s exists: %s",
                filename,
                result.stderr.strip(),
            )

        except subprocess.TimeoutExpired:
            logging.warning(
                "Timeout checking %s on Pi",
                filename,
            )

        except Exception as exc:
            logging.warning(
                "Error checking %s: %s",
                filename,
                exc,
            )

        wait_before_retry(attempt)

    return None


# ============================================================
# Download one file
# ============================================================

def download_file(filename):
    remote_file = f"{PI_DATA_DIR}/{filename}"

    local_filename = f"{STATION_NAME}_{filename}"
    local_file = LOCAL_DATA_DIR / local_filename

    for attempt in range(1, MAX_RETRIES + 1):

        logging.info(
            "Downloading %s (attempt %d/%d)",
            filename,
            attempt,
            MAX_RETRIES,
        )

        command = [
            "sshpass",
            "-p",
            PI_PASSWORD,
            "scp",
            "-o",
            f"ConnectTimeout={CONNECT_TIMEOUT}",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{PI_USER}@{PI_HOST}:{remote_file}",
            str(local_file),
        ]

        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=120,
            )

            if result.returncode == 0:
                logging.info(
                    "Downloaded: %s",
                    local_file.name,
                )
                return local_file

            logging.warning(
                "Download failed: %s",
                result.stderr.strip(),
            )

        except subprocess.TimeoutExpired:
            logging.warning(
                "Download timed out: %s",
                filename,
            )

        except Exception as exc:
            logging.warning(
                "Download error for %s: %s",
                filename,
                exc,
            )

        wait_before_retry(attempt)

    logging.error(
        "Failed to download %s after %d attempts",
        filename,
        MAX_RETRIES,
    )

    return None


# ============================================================
# Download files for one date
# ============================================================

def download_date(date_string):

    filenames = [
        f"R_GAIN_LOW_{date_string}.csv",
        f"R_GAIN_MED_{date_string}.csv",
        f"R_GAIN_MAX_{date_string}.csv",
        f"R{date_string}.csv",
    ]

    downloaded_files = []

    logging.info(
        "Looking for data files for %s",
        date_string,
    )

    for filename in filenames:

        exists = remote_file_exists(filename)

        if exists is False:
            logging.info(
                "File does not exist on Pi: %s",
                filename,
            )
            continue

        if exists is None:
            logging.error(
                "Unable to check %s because communication with Pi failed",
                filename,
            )
            return None

        local_file = download_file(filename)

        if local_file is None:
            # File exists but we could not download it.
            # Treat this as a genuine failure.
            return None

        downloaded_files.append(local_file)

    return downloaded_files


# ============================================================
# Create archive
# ============================================================

def create_archive(files, date_string):

    archive_name = f"Lux_{STATION_NAME}_{date_string}.bz2"
    archive_path = LOCAL_DATA_DIR / archive_name

    logging.info(
        "Creating archive %s containing %d file(s)",
        archive_name,
        len(files),
    )

    try:
        # Although the extension is .bz2, this is a tar archive
        # compressed using bzip2 so it can contain multiple files.
        with tarfile.open(archive_path, mode="w:bz2") as archive:

            for file_path in files:
                logging.info(
                    "Adding to archive: %s",
                    file_path.name,
                )

                archive.add(
                    file_path,
                    arcname=file_path.name,
                )

        logging.info(
            "Archive created successfully: %s",
            archive_path,
        )

        return archive_path

    except Exception as exc:
        logging.error(
            "Failed to create archive: %s",
            exc,
        )

        return None


# ============================================================
# Upload archive using SFTP ONLY
# ============================================================

def upload_archive(archive_path):

    if not SSH_PRIVATE_KEY.exists():
        logging.error(
            "SSH private key not found: %s",
            SSH_PRIVATE_KEY,
        )
        return False

    for attempt in range(1, MAX_RETRIES + 1):

        logging.info(
            "Uploading %s to %s@%s (attempt %d/%d)",
            archive_path.name,
            GMN_USER,
            GMN_HOST,
            attempt,
            MAX_RETRIES,
        )

        batch_filename = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                delete=False,
                prefix="lux_sftp_",
                suffix=".txt",
            ) as batch:

                # SFTP ONLY - no SSH command is used on gmn.uwo.ca

                batch.write("cd /home/rmsuser/files\n")

                # Ignore error if directory already exists
                batch.write("-mkdir lux_data\n")

                batch.write("cd lux_data\n")

                batch.write(
                    f'put "{archive_path}"\n'
                )

                batch.write("quit\n")

                batch_filename = batch.name

            command = [
                "sftp",
                "-i",
                str(SSH_PRIVATE_KEY),
                "-o",
                "BatchMode=yes",
                "-o",
                f"ConnectTimeout={CONNECT_TIMEOUT}",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-b",
                batch_filename,
                f"{GMN_USER}@{GMN_HOST}",
            ]

            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=300,
            )

            if result.returncode == 0:

                logging.info(
                    "Upload successful: %s",
                    archive_path.name,
                )

                return True

            logging.warning(
                "SFTP upload failed: %s",
                result.stderr.strip(),
            )

        except subprocess.TimeoutExpired:

            logging.warning(
                "SFTP upload timed out"
            )

        except Exception as exc:

            logging.warning(
                "SFTP upload error: %s",
                exc,
            )

        finally:

            if batch_filename:
                try:
                    os.unlink(batch_filename)
                except OSError:
                    pass

        wait_before_retry(attempt)

    logging.error(
        "Upload failed after %d attempts: %s",
        MAX_RETRIES,
        archive_path.name,
    )

    return False


# ============================================================
# Process one date
# ============================================================

def process_date(date_string):

    logging.info(
        "============================================================"
    )

    logging.info(
        "Processing UTC date %s",
        date_string,
    )

    files = download_date(date_string)

    # None means a real communications/download failure.
    if files is None:

        logging.error(
            "Could not obtain data for %s - keeping date pending",
            date_string,
        )

        return False

    # Zero files is different from an incomplete day.
    # There is nothing that can usefully be archived.
    if len(files) == 0:

        logging.warning(
            "No data files found for %s - keeping date pending",
            date_string,
        )

        return False

    if len(files) < 4:

        logging.warning(
            "Only %d of 4 files exist for %s - "
            "archiving and sending available files",
            len(files),
            date_string,
        )

    else:

        logging.info(
            "All 4 files found for %s",
            date_string,
        )

    archive_path = create_archive(
        files,
        date_string,
    )

    if archive_path is None:

        logging.error(
            "Archive creation failed for %s - keeping date pending",
            date_string,
        )

        return False

    if not upload_archive(archive_path):

        logging.error(
            "Upload failed for %s - keeping date pending",
            date_string,
        )

        return False

    logging.info(
        "Date %s completed successfully",
        date_string,
    )

    return True


# ============================================================
# Main
# ============================================================

def main():

    setup_logging()

    logging.info("")
    logging.info("Lux automatic transfer started")
    logging.info("Station: %s", STATION_NAME)

    previous_date = get_previous_utc_date()

    pending_dates = load_pending_dates()

    # Always add the just-completed UTC date.
    if previous_date not in pending_dates:
        pending_dates.append(previous_date)

    pending_dates = sorted(set(pending_dates))

    # Save immediately so even an unexpected crash does not lose
    # the date we intended to process.
    save_pending_dates(pending_dates)

    logging.info(
        "Dates awaiting processing: %s",
        ", ".join(pending_dates),
    )

    completed_dates = []

    # Oldest dates are processed first.
    for date_string in pending_dates:

        success = process_date(date_string)

        if success:
            completed_dates.append(date_string)

    # Remove only dates which were successfully uploaded.
    remaining_dates = [
        date_string
        for date_string in pending_dates
        if date_string not in completed_dates
    ]

    save_pending_dates(remaining_dates)

    logging.info(
        "============================================================"
    )

    if remaining_dates:

        logging.warning(
            "Dates still pending: %s",
            ", ".join(remaining_dates),
        )

    else:

        logging.info(
            "No dates remain pending"
        )

    logging.info(
        "Lux automatic transfer finished"
    )

    logging.info("")


if __name__ == "__main__":
    main()
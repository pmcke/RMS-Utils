#!/usr/bin/env python3

import json
import logging
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

STATION_NAME = "NZ005A"

# Earliest UTC date that this installation is allowed to send.
# Format: YYYYMMDD
START_DATE = "20261001"

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

# SSH PRIVATE key used by SFTP
SSH_PRIVATE_KEY = Path.home() / ".ssh" / "id_rsa"

# Persistent files
LOG_FILE = LOCAL_DATA_DIR / "lux_transfer.log"
UPLOADED_FILE = LOCAL_DATA_DIR / "uploaded_dates.json"

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

    logging.Formatter.converter = time.gmtime


# ============================================================
# Uploaded-date management
# ============================================================

def load_uploaded_dates():
    if not UPLOADED_FILE.exists():
        return []

    try:
        with open(UPLOADED_FILE, "r") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

    except Exception as exc:
        logging.error(
            "Could not read uploaded dates file: %s",
            exc,
        )

    return []


def save_uploaded_dates(dates):
    """
    Safely save uploaded dates.

    Write to a temporary file first and then replace the real file,
    reducing the chance of corrupting the JSON if the machine loses
    power while writing it.
    """

    temp_file = UPLOADED_FILE.with_suffix(".tmp")

    try:
        with open(temp_file, "w") as f:
            json.dump(sorted(set(dates)), f, indent=2)

        os.replace(temp_file, UPLOADED_FILE)

    except Exception as exc:
        logging.error(
            "Could not save uploaded dates file: %s",
            exc,
        )


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
# Find available dates on Pi
# ============================================================

def get_available_dates():
    """
    Get filenames from the Pi and determine which UTC dates have
    radiometer data available.

    Recognised filenames:

        R_GAIN_LOW_YYYYMMDD.csv
        R_GAIN_MED_YYYYMMDD.csv
        R_GAIN_MAX_YYYYMMDD.csv
        RYYYYMMDD.csv

    Returns a sorted list of dates, or None if the Pi could not
    be contacted.
    """

    command_on_pi = f"ls -1 {PI_DATA_DIR}"

    for attempt in range(1, MAX_RETRIES + 1):

        logging.info(
            "Checking available dates on Pi (attempt %d/%d)",
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
            command_on_pi,
        ]

        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=CONNECT_TIMEOUT + 30,
            )

            if result.returncode == 0:

                dates = set()

                patterns = [
                    r"^R_GAIN_LOW_(\d{8})\.csv$",
                    r"^R_GAIN_MED_(\d{8})\.csv$",
                    r"^R_GAIN_MAX_(\d{8})\.csv$",
                    r"^R(\d{8})\.csv$",
                ]

                for filename in result.stdout.splitlines():

                    filename = filename.strip()

                    for pattern in patterns:
                        match = re.match(pattern, filename)

                        if match:
                            dates.add(match.group(1))
                            break

                return sorted(dates)

            logging.warning(
                "Could not list Pi data directory: %s",
                result.stderr.strip(),
            )

        except subprocess.TimeoutExpired:
            logging.warning(
                "Timeout while checking Pi data directory"
            )

        except Exception as exc:
            logging.warning(
                "Error checking Pi data directory: %s",
                exc,
            )

        wait_before_retry(attempt)

    return None


# ============================================================
# Determine exactly which files exist for a date
# ============================================================

def get_files_for_date(date_string):
    """
    Determine which of the four possible files actually exist.

    Returns:
        list = filenames that exist
        None = communication failure
    """

    possible_files = [
        f"R_GAIN_LOW_{date_string}.csv",
        f"R_GAIN_MED_{date_string}.csv",
        f"R_GAIN_MAX_{date_string}.csv",
        f"R{date_string}.csv",
    ]

    command_on_pi = f"ls -1 {PI_DATA_DIR}"

    for attempt in range(1, MAX_RETRIES + 1):

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
            command_on_pi,
        ]

        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=CONNECT_TIMEOUT + 30,
            )

            if result.returncode == 0:

                existing_files = set(
                    line.strip()
                    for line in result.stdout.splitlines()
                )

                return [
                    filename
                    for filename in possible_files
                    if filename in existing_files
                ]

            logging.warning(
                "Could not obtain file list from Pi: %s",
                result.stderr.strip(),
            )

        except subprocess.TimeoutExpired:
            logging.warning(
                "Timeout obtaining file list from Pi"
            )

        except Exception as exc:
            logging.warning(
                "Error obtaining file list: %s",
                exc,
            )

        wait_before_retry(attempt)

    return None


# ============================================================
# Download a file
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
# Create archive
# ============================================================

def create_archive(files, date_string):

    archive_name = (
        f"Lux_{STATION_NAME}_{date_string}.bz2"
    )

    archive_path = (
        LOCAL_DATA_DIR / archive_name
    )

    logging.info(
        "Creating archive %s containing %d file(s)",
        archive_name,
        len(files),
    )

    try:

        with tarfile.open(
            archive_path,
            mode="w:bz2",
        ) as archive:

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
# Upload using SFTP ONLY
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
            "Uploading %s to %s@%s "
            "(attempt %d/%d)",
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

                # GMN permits SFTP only.
                batch.write(
                    "cd /home/rmsuser/files\n"
                )

                # Ignore failure if lux_data already exists.
                batch.write(
                    "-mkdir lux_data\n"
                )

                batch.write(
                    "cd lux_data\n"
                )

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
# Process one UTC date
# ============================================================

def process_date(date_string):

    logging.info(
        "============================================================"
    )

    logging.info(
        "Processing UTC date %s",
        date_string,
    )

    filenames = get_files_for_date(date_string)

    if filenames is None:

        logging.error(
            "Could not obtain file list for %s",
            date_string,
        )

        return False

    if len(filenames) == 0:

        logging.warning(
            "No files found for %s",
            date_string,
        )

        return False

    if len(filenames) < 4:

        logging.warning(
            "Only %d of 4 files exist for %s - "
            "sending available files",
            len(filenames),
            date_string,
        )

    else:

        logging.info(
            "All 4 files found for %s",
            date_string,
        )

    downloaded_files = []

    for filename in filenames:

        local_file = download_file(filename)

        if local_file is None:

            logging.error(
                "Could not download all available "
                "files for %s",
                date_string,
            )

            return False

        downloaded_files.append(local_file)

    archive_path = create_archive(
        downloaded_files,
        date_string,
    )

    if archive_path is None:

        return False

    if not upload_archive(archive_path):

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
    logging.info(
        "Lux automatic transfer started"
    )

    logging.info(
        "Station: %s",
        STATION_NAME,
    )

    logging.info(
        "Start date: %s",
        START_DATE,
    )

    # Current UTC date must never be sent because it
    # has not finished yet.
    today_utc = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d")

    logging.info(
        "Current UTC date: %s",
        today_utc,
    )

    # --------------------------------------------------------
    # Ask the Pi which dates actually exist.
    # --------------------------------------------------------

    available_dates = get_available_dates()

    if available_dates is None:

        logging.error(
            "Unable to contact Pi after retries. "
            "Nothing will be processed this run."
        )

        logging.info(
            "Lux automatic transfer finished"
        )

        return

    logging.info(
        "Pi contains %d relevant date(s)",
        len(available_dates),
    )

    # --------------------------------------------------------
    # Read dates that have already been successfully sent.
    # --------------------------------------------------------

    uploaded_dates = load_uploaded_dates()

    uploaded_set = set(uploaded_dates)

    # --------------------------------------------------------
    # Determine what actually needs sending.
    #
    # Must:
    #   - be on the Pi
    #   - be START_DATE or later
    #   - be earlier than today UTC
    #   - not already have been successfully uploaded
    # --------------------------------------------------------

    dates_to_send = [
        date_string
        for date_string in available_dates
        if date_string >= START_DATE
        and date_string < today_utc
        and date_string not in uploaded_set
    ]

    dates_to_send.sort()

    if not dates_to_send:

        logging.info(
            "No data awaiting upload"
        )

        logging.info(
            "Lux automatic transfer finished"
        )

        return

    logging.info(
        "Dates awaiting upload: %s",
        ", ".join(dates_to_send),
    )

    # --------------------------------------------------------
    # Process oldest unsent date first.
    # --------------------------------------------------------

    for date_string in dates_to_send:

        success = process_date(
            date_string
        )

        if success:

            uploaded_set.add(
                date_string
            )

            # Save immediately after every successful upload.
            # If the machine subsequently crashes, we still
            # know this date was successfully sent.
            save_uploaded_dates(
                uploaded_set
            )

        else:

            logging.error(
                "Date %s was not successfully sent. "
                "It will be tried again on the next run.",
                date_string,
            )

            # Continue with other dates rather than allowing
            # one failed date to prevent later dates being sent.

    logging.info(
        "============================================================"
    )

    logging.info(
        "Lux automatic transfer finished"
    )

    logging.info("")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
""" Upload the Fireballs360 lux meter data to the GMN server and monitor the Pi Zero clock.

The lux meter is read by a Raspberry Pi Zero which writes one file per channel per UTC day. This script runs
on the main (Ubuntu) machine and has two modes:

    1) Daily upload (default). Downloads the files of every finished UTC day that hasn't been uploaded yet
       from the Pi Zero, packs them together with the clock status of that day into
       Lux_<STATION>_<YYYYMMDD>.tar.bz2 and uploads the archive to the station's lux_data directory on the
       GMN server. Days that fail are retried on the next run.

    2) Clock monitoring (--clock). The lux timestamps come from the Pi Zero system clock, so they are only
       as good as its synchronization. Every run queries chrony on the Pi Zero and appends one line to
       clock/<STATION>_CLOCK_<YYYYMMDD>.csv: NOMINAL, DEGRADED (synchronized, but the worst-case clock
       error is above CLOCK_MAX_ERROR), UNSYNCED or UNKNOWN (Pi Zero or chrony not reachable). The daily
       upload adds this file and a summary (<STATION>_CLOCK_SUMMARY_<YYYYMMDD>.json) to the archive, so the
       intervals with unreliable timestamps can be flagged on the server.

One-time setup:

    - Log into the Pi Zero with the existing RMS SSH key of the main machine (no new key is needed), then
      change the Pi Zero password, as the old one was published:

        ssh-copy-id -i ~/.ssh/id_rsa.pub fireballslux@192.168.6.50
        ssh fireballslux@192.168.6.50 passwd

    - Install chrony on the Pi Zero (it replaces systemd-timesyncd) and check that it is synchronized:

        ssh fireballslux@192.168.6.50 "sudo apt install -y chrony && chronyc tracking"

    - Set STATION_NAME and START_DATE below, then add two crontab entries (crontab -e):

        */10 * * * * /usr/bin/python3 /home/USER/RMS-Utils/upload_lux_data.py --clock
        7 0 * * * /usr/bin/python3 /home/USER/RMS-Utils/upload_lux_data.py
"""

import argparse
import fcntl
import json
import logging
import os
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


### CONFIGURATION ###

# Station code of the main camera, used for the GMN server account and the file names
STATION_NAME = "NZ005A"

# Earliest UTC date (YYYYMMDD) that this installation will upload
START_DATE = "20261001"

# Pi Zero
PI_HOST = "192.168.6.50"
PI_USER = "fireballslux"
PI_DATA_DIR = "/home/fireballslux/radiometer_data"

# SSH key used both for the Pi Zero and the GMN server (the existing RMS key)
SSH_PRIVATE_KEY = Path.home()/".ssh"/"id_rsa"

# Local storage on the main machine
LOCAL_DATA_DIR = Path.home()/"Lux_data_auto"
CLOCK_DIR = LOCAL_DATA_DIR/"clock"
LOG_FILE = LOCAL_DATA_DIR/"lux_transfer.log"
UPLOADED_FILE = LOCAL_DATA_DIR/"uploaded_dates.json"
LOCK_FILE = LOCAL_DATA_DIR/"upload_lux_data.lock"

# GMN server
GMN_HOST = "gmn.uwo.ca"
GMN_USER = STATION_NAME.lower()
GMN_REMOTE_DIR = "/home/rmsuser/files/lux_data"

# Channels written by the Pi Zero every UTC day, {:s} is the date in the YYYYMMDD format
LUX_FILE_TEMPLATES = [
    "R_GAIN_LOW_{:s}.csv",
    "R_GAIN_MED_{:s}.csv",
    "R_GAIN_MAX_{:s}.csv",
    "R{:s}.csv",
]

# Clock monitoring. The worst-case clock error is estimated by chrony as
# |system time offset| + root dispersion + root delay/2 (seconds)
CLOCK_MAX_ERROR = 0.05
CLOCK_INTERVAL_MIN = 10
CLOCK_MIN_COVERAGE = 0.9
CLOCK_KEEP_DAYS = 60

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 60
CONNECT_TIMEOUT = 30

# Clock statuses, from best to worst
CLOCK_STATUSES = ["NOMINAL", "UNKNOWN", "DEGRADED", "UNSYNCED"]

CLOCK_LOG_HEADER = "sample_time_utc,status,max_error_s,system_offset_s,root_delay_s,root_dispersion_s," \
    "stratum,leap_status,reference\n"


log = logging.getLogger("upload_lux_data")


def setupLogging():
    """ Log to the console and to LOG_FILE, with UTC timestamps. """

    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s UTC %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    formatter.converter = time.gmtime

    for handler in [logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]:
        handler.setFormatter(formatter)
        log.addHandler(handler)

    log.setLevel(logging.INFO)


def acquireLock(lock_path):
    """ Make sure only one instance runs at a time.

    Arguments:
        lock_path: [Path] Path to the lock file.

    Return:
        [file object or None] Open lock file (keep a reference until the end of the run), or None if another
            instance holds the lock.
    """

    lock_file = open(lock_path, "w")

    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

    except OSError:
        lock_file.close()
        return None

    return lock_file


def sshOptions():
    """ Common options for ssh, scp and sftp. Key authentication only, never prompt for a password. """

    return ["-i", str(SSH_PRIVATE_KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout={:d}".format(CONNECT_TIMEOUT),
        "-o", "StrictHostKeyChecking=accept-new"]


def runCommand(command, description, timeout, retries=MAX_RETRIES):
    """ Run a command, retrying on failure.

    Arguments:
        command: [list] Command and its arguments.
        description: [str] What the command does, used in the log.
        timeout: [float] Timeout of one attempt in seconds.

    Keyword arguments:
        retries: [int] Number of attempts.

    Return:
        [subprocess.CompletedProcess or None] Result of the first successful attempt, None if all failed.
    """

    for attempt in range(1, retries + 1):

        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)

            if result.returncode == 0:
                return result

            log.warning("{:s} failed (attempt {:d}/{:d}): {:s}".format(description, attempt, retries,
                result.stderr.strip()))

        except subprocess.TimeoutExpired:
            log.warning("{:s} timed out (attempt {:d}/{:d})".format(description, attempt, retries))

        except OSError as e:
            log.warning("{:s} could not be run (attempt {:d}/{:d}): {:s}".format(description, attempt, retries,
                str(e)))

        if attempt < retries:
            time.sleep(RETRY_DELAY_SECONDS)

    log.error("{:s} failed after {:d} attempts".format(description, retries))

    return None


def runOnPi(remote_command, description, timeout=CONNECT_TIMEOUT + 30, retries=MAX_RETRIES):
    """ Run a command on the Pi Zero over SSH. See runCommand for the arguments and the return value. """

    command = ["ssh"] + sshOptions() + ["{:s}@{:s}".format(PI_USER, PI_HOST), remote_command]

    return runCommand(command, description, timeout, retries=retries)



### CLOCK MONITORING ###

def parseChronyTracking(output, max_error=CLOCK_MAX_ERROR):
    """ Parse the output of 'chronyc -c tracking' and classify the clock synchronization.

    Arguments:
        output: [str] One CSV line with 14 fields: reference ID, reference name, stratum, reference time,
            system time offset, last offset, RMS offset, frequency, residual frequency, skew, root delay,
            root dispersion, update interval, leap status.

    Keyword arguments:
        max_error: [float] Largest acceptable worst-case clock error in seconds.

    Return:
        [dict] Clock status, see CLOCK_LOG_HEADER for the keys.
    """

    fields = output.strip().split(",")

    if len(fields) < 14:
        raise ValueError("Unexpected chronyc output: {:s}".format(output.strip()))

    stratum = int(fields[2])
    system_offset = float(fields[4])
    root_delay = float(fields[10])
    root_dispersion = float(fields[11])
    leap_status = fields[13]

    # Worst-case error of the system clock as defined in the chrony documentation
    error = abs(system_offset) + root_dispersion + root_delay/2

    if (leap_status == "Not synchronised") or (stratum == 0) or (stratum >= 16):
        status = "UNSYNCED"

    elif error > max_error:
        status = "DEGRADED"

    else:
        status = "NOMINAL"

    return {
        "status": status,
        "max_error_s": error,
        "system_offset_s": system_offset,
        "root_delay_s": root_delay,
        "root_dispersion_s": root_dispersion,
        "stratum": stratum,
        "leap_status": leap_status,
        "reference": fields[1],
    }


def clockLogPath(date_str):
    """ Path to the local clock log of the given UTC date (YYYYMMDD). """

    return CLOCK_DIR/"{:s}_CLOCK_{:s}.csv".format(STATION_NAME, date_str)


def logClockStatus():
    """ Query chrony on the Pi Zero and append the result to today's clock log.

    Return:
        [dict] Clock status, see parseChronyTracking.
    """

    now = datetime.now(timezone.utc)

    # No retries, the next sample is only CLOCK_INTERVAL_MIN away
    result = runOnPi("chronyc -c tracking", "Querying chrony on the Pi Zero", retries=1)

    clock = None
    if result is not None:

        try:
            clock = parseChronyTracking(result.stdout)

        except ValueError as e:
            log.error(str(e))

    if clock is None:
        clock = {"status": "UNKNOWN", "max_error_s": "", "system_offset_s": "", "root_delay_s": "",
            "root_dispersion_s": "", "stratum": "", "leap_status": "", "reference": ""}

    CLOCK_DIR.mkdir(parents=True, exist_ok=True)

    log_path = clockLogPath(now.strftime("%Y%m%d"))
    new_file = not log_path.exists()

    with open(log_path, "a") as f:

        if new_file:
            f.write(CLOCK_LOG_HEADER)

        f.write("{:s},{:s},{},{},{},{},{},{:s},{:s}\n".format(now.strftime("%Y-%m-%dT%H:%M:%S"),
            clock["status"], clock["max_error_s"], clock["system_offset_s"], clock["root_delay_s"],
            clock["root_dispersion_s"], clock["stratum"], clock["leap_status"], clock["reference"]))

    if clock["status"] == "NOMINAL":
        log.info("Pi Zero clock NOMINAL, max error {:.4f} s".format(clock["max_error_s"]))

    else:
        log.warning("Pi Zero clock {:s}".format(clock["status"]))

    # Delete old clock logs
    cutoff = (now - timedelta(days=CLOCK_KEEP_DAYS)).strftime("%Y%m%d")
    for old_path in CLOCK_DIR.glob("{:s}_CLOCK_*.csv".format(STATION_NAME)):

        if old_path.stem.split("_")[-1] < cutoff:
            old_path.unlink()

    return clock


def summarizeClockLog(date_str):
    """ Summarize the clock log of the given UTC date.

    The day is UNSYNCED or DEGRADED if any sample was, NOMINAL if at least CLOCK_MIN_COVERAGE of the expected
    samples were taken and all were NOMINAL, and UNKNOWN otherwise. The individual samples in the clock log
    show which part of the day is affected.

    Arguments:
        date_str: [str] UTC date in the YYYYMMDD format.

    Return:
        [dict] Summary of the clock status for the day.
    """

    expected = 24*60//CLOCK_INTERVAL_MIN

    counts = {status: 0 for status in CLOCK_STATUSES}
    errors = []

    log_path = clockLogPath(date_str)
    if log_path.exists():

        with open(log_path) as f:

            # Skip the header
            next(f, None)

            for line in f:

                fields = line.strip().split(",")
                if len(fields) < 3 or fields[1] not in counts:
                    continue

                counts[fields[1]] += 1

                if fields[2]:
                    errors.append(float(fields[2]))

    known = counts["NOMINAL"] + counts["DEGRADED"] + counts["UNSYNCED"]

    if counts["UNSYNCED"] > 0:
        status = "UNSYNCED"

    elif counts["DEGRADED"] > 0:
        status = "DEGRADED"

    elif known >= CLOCK_MIN_COVERAGE*expected:
        status = "NOMINAL"

    else:
        status = "UNKNOWN"

    return {
        "station": STATION_NAME,
        "date": date_str,
        "status": status,
        "samples": sum(counts.values()),
        "expected_samples": expected,
        "counts": counts,
        "max_error_s": max(errors) if errors else None,
        "threshold_s": CLOCK_MAX_ERROR,
    }



### DAILY UPLOAD ###

def loadUploadedDates():
    """ Return the set of dates which were already uploaded. """

    if not UPLOADED_FILE.exists():
        return set()

    try:
        with open(UPLOADED_FILE) as f:
            data = json.load(f)

        if isinstance(data, list):
            return set(data)

    except (OSError, ValueError) as e:
        log.error("Could not read {:s}: {:s}".format(str(UPLOADED_FILE), str(e)))

    return set()


def saveUploadedDates(dates):
    """ Save the uploaded dates. Writes to a temporary file first so a power cut can't corrupt the list.

    Arguments:
        dates: [set] Uploaded dates in the YYYYMMDD format.
    """

    temp_path = UPLOADED_FILE.with_suffix(".tmp")

    try:
        with open(temp_path, "w") as f:
            json.dump(sorted(dates), f, indent=2)

        os.replace(temp_path, UPLOADED_FILE)

    except OSError as e:
        log.error("Could not save {:s}: {:s}".format(str(UPLOADED_FILE), str(e)))


def listPiFiles():
    """ List the data directory on the Pi Zero.

    Return:
        [set or None] File names, None if the Pi Zero could not be reached.
    """

    result = runOnPi("ls -1 {:s}".format(PI_DATA_DIR), "Listing the Pi Zero data directory")

    if result is None:
        return None

    return set(line.strip() for line in result.stdout.splitlines())


def availableDates(pi_files):
    """ Return the sorted list of UTC dates (YYYYMMDD) for which the Pi Zero has data.

    Arguments:
        pi_files: [set] File names in the Pi Zero data directory.
    """

    patterns = [re.compile("^" + re.escape(template).replace(r"\{:s\}", r"(\d{8})") + "$")
        for template in LUX_FILE_TEMPLATES]

    dates = set()
    for file_name in pi_files:

        for pattern in patterns:

            match = pattern.match(file_name)
            if match:
                dates.add(match.group(1))
                break

    return sorted(dates)


def downloadFile(file_name):
    """ Download a file from the Pi Zero, prefixing the local copy with the station name.

    Arguments:
        file_name: [str] Name of the file in the Pi Zero data directory.

    Return:
        [Path or None] Path to the local copy, None if the download failed.
    """

    local_path = LOCAL_DATA_DIR/"{:s}_{:s}".format(STATION_NAME, file_name)

    command = ["scp"] + sshOptions() + ["{:s}@{:s}:{:s}".format(PI_USER, PI_HOST,
        posixpath.join(PI_DATA_DIR, file_name)), str(local_path)]

    if runCommand(command, "Downloading {:s}".format(file_name), timeout=120) is None:
        return None

    log.info("Downloaded {:s}".format(local_path.name))

    return local_path


def createArchive(file_paths, clock_summary, date_str):
    """ Pack the lux files, the clock log and the clock summary of one day into a .tar.bz2 archive.

    Arguments:
        file_paths: [list] Paths to the lux files to include.
        clock_summary: [dict] Output of summarizeClockLog.
        date_str: [str] UTC date in the YYYYMMDD format.

    Return:
        [Path or None] Path to the archive, None if it could not be created.
    """

    archive_path = LOCAL_DATA_DIR/"Lux_{:s}_{:s}.tar.bz2".format(STATION_NAME, date_str)

    try:
        with tarfile.open(archive_path, mode="w:bz2") as archive:

            for file_path in file_paths:
                archive.add(file_path, arcname=file_path.name)

            clock_log = clockLogPath(date_str)
            if clock_log.exists():
                archive.add(clock_log, arcname=clock_log.name)

            # The summary only exists inside the archive
            with tempfile.TemporaryDirectory() as temp_dir:

                summary_path = Path(temp_dir)/"{:s}_CLOCK_SUMMARY_{:s}.json".format(STATION_NAME, date_str)
                with open(summary_path, "w") as f:
                    json.dump(clock_summary, f, indent=2)

                archive.add(summary_path, arcname=summary_path.name)

    except (OSError, tarfile.TarError) as e:
        log.error("Could not create {:s}: {:s}".format(archive_path.name, str(e)))
        return None

    log.info("Created {:s}".format(archive_path.name))

    return archive_path


def uploadArchive(archive_path):
    """ Upload the archive to the GMN server over SFTP (the server doesn't allow a shell).

    Arguments:
        archive_path: [Path] Path to the archive.

    Return:
        [bool] True if the upload succeeded.
    """

    if not SSH_PRIVATE_KEY.exists():
        log.error("SSH key not found: {:s}".format(str(SSH_PRIVATE_KEY)))
        return False

    parent_dir, dir_name = posixpath.split(GMN_REMOTE_DIR)

    # The "-" prefix ignores the error if the directory already exists
    batch_commands = "cd {:s}\n-mkdir {:s}\ncd {:s}\nput \"{:s}\"\nquit\n".format(parent_dir, dir_name, dir_name,
        str(archive_path))

    with tempfile.NamedTemporaryFile(mode="w", prefix="lux_sftp_", suffix=".txt") as batch:

        batch.write(batch_commands)
        batch.flush()

        command = ["sftp"] + sshOptions() + ["-b", batch.name, "{:s}@{:s}".format(GMN_USER, GMN_HOST)]

        result = runCommand(command, "Uploading {:s}".format(archive_path.name), timeout=300)

    if result is None:
        return False

    log.info("Uploaded {:s}".format(archive_path.name))

    return True


def processDate(date_str, pi_files):
    """ Download, archive and upload the data of one UTC day.

    Arguments:
        date_str: [str] UTC date in the YYYYMMDD format.
        pi_files: [set] File names in the Pi Zero data directory.

    Return:
        [bool] True if the day was uploaded.
    """

    log.info("Processing {:s}".format(date_str))

    file_names = [template.format(date_str) for template in LUX_FILE_TEMPLATES
        if template.format(date_str) in pi_files]

    if len(file_names) < len(LUX_FILE_TEMPLATES):
        log.warning("Only {:d} of {:d} files exist for {:s}, sending the available ones".format(len(file_names),
            len(LUX_FILE_TEMPLATES), date_str))

    file_paths = []
    for file_name in file_names:

        local_path = downloadFile(file_name)
        if local_path is None:
            return False

        file_paths.append(local_path)

    clock_summary = summarizeClockLog(date_str)
    log.info("Clock status for {:s}: {:s} ({:d}/{:d} samples)".format(date_str, clock_summary["status"],
        clock_summary["samples"], clock_summary["expected_samples"]))

    archive_path = createArchive(file_paths, clock_summary, date_str)
    if archive_path is None:
        return False

    return uploadArchive(archive_path)


def uploadNewDates():
    """ Upload every finished UTC day from START_DATE on which hasn't been uploaded yet, oldest first. """

    # Today is still being written to
    today_utc = datetime.now(timezone.utc).strftime("%Y%m%d")

    pi_files = listPiFiles()
    if pi_files is None:
        log.error("The Pi Zero could not be reached, nothing uploaded")
        return

    uploaded_dates = loadUploadedDates()

    dates_to_send = [date_str for date_str in availableDates(pi_files)
        if (START_DATE <= date_str < today_utc) and (date_str not in uploaded_dates)]

    if not dates_to_send:
        log.info("No data awaiting upload")
        return

    log.info("Dates awaiting upload: {:s}".format(", ".join(dates_to_send)))

    for date_str in dates_to_send:

        # A failed day doesn't stop the later ones, it will be retried on the next run
        if processDate(date_str, pi_files):

            # Save after every day so a crash doesn't cause the day to be uploaded again
            uploaded_dates.add(date_str)
            saveUploadedDates(uploaded_dates)

        else:
            log.error("{:s} was not uploaded, it will be retried on the next run".format(date_str))



if __name__ == "__main__":

    ### COMMAND LINE ARGUMENTS

    # Init the command line arguments parser
    arg_parser = argparse.ArgumentParser(description="Upload the Fireballs360 lux meter data to the GMN server.")

    arg_parser.add_argument("--clock", action="store_true",
        help="Only log the Pi Zero clock status (run every {:d} minutes).".format(CLOCK_INTERVAL_MIN))

    # Parse the command line arguments
    cml_args = arg_parser.parse_args()

    #########################

    setupLogging()

    # The clock check and the upload use separate locks, so a long upload doesn't skip clock samples
    lock_path = LOCK_FILE.with_suffix(".clock.lock") if cml_args.clock else LOCK_FILE
    lock = acquireLock(lock_path)

    if lock is None:
        log.warning("Another instance is already running, exiting")
        sys.exit(1)

    if cml_args.clock:
        logClockStatus()

    else:
        log.info("Lux upload started for {:s}".format(STATION_NAME))
        uploadNewDates()
        log.info("Lux upload finished")

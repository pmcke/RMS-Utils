#!/usr/bin/env python3
"""
Wrapper for SetiUploader that first runs logMeteorStats.sh
with the stationID from config, logging its output, then
invokes the original SetiUploader in the same way as before.
"""

import subprocess
import os
import sys
import traceback
import contextlib
from datetime import datetime

# --- Add both RMS root and CAMS subfolder to import path ---
sys.path.insert(0, "/home/rms/source/RMS/CAMS")
sys.path.insert(0, os.path.dirname(__file__))

import RMS.ConfigReader as cr

# Try importing SetiUploader safely
try:
    from SetiUploader import rmsExternal as real_rmsExternal
    SETI_UPLOADER_AVAILABLE = True
    print("SetiUploader.py found and loaded successfully.")
except ModuleNotFoundError:
    SETI_UPLOADER_AVAILABLE = False
    real_rmsExternal = None
    print("Warning: SetiUploader.py not found — skipping upload step.")


def rmsExternal(captured_night_dir, archived_night_dir, config):
    """Runs logMeteorStats.sh (logging output) before invoking SetiUploader."""

    # --- Define base paths dynamically ---
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base_dir, exist_ok=True)
    script_path = os.path.join(base_dir, "logMeteorStats.sh")
    log_path = os.path.join(base_dir, "logMeteorStats.log")

    # --- Step 1: Run logMeteorStats.sh ---
    try:
        with open(log_path, "a") as log_file:
            log_file.write("\n" + "=" * 60 + "\n")
            log_file.write(f"Run started: {datetime.utcnow().isoformat()} UTC\n")

            if hasattr(config, "stationID") and config.stationID:
                cmd = [script_path, str(config.stationID)]
                log_file.write(f"Executing: {' '.join(cmd)}\n")
                log_file.flush()

                result = subprocess.run(
                    cmd,
                    stdout=log_file,
                    stderr=log_file,
                    check=True,
                    text=True,
                )

                log_file.write(f"Completed successfully with return code {result.returncode}\n")
            else:
                msg = "Warning: No stationID found in config, skipping logMeteorStats.sh\n"
                log_file.write(msg)
                print(msg)

    except subprocess.CalledProcessError as e:
        with open(log_path, "a") as log_file:
            log_file.write(f"Error running logMeteorStats.sh: {e}\n")
        print(f"Error running logMeteorStats.sh: {e}")

    except Exception as e:
        with open(log_path, "a") as log_file:
            log_file.write("Unexpected error running logMeteorStats.sh:\n")
            traceback.print_exc(file=log_file)
        print("Unexpected error running logMeteorStats.sh:")
        traceback.print_exc()

    # --- Step 2: Continue with the original SetiUploader ---
    print("Now running SetiUploader.py as before...")

    if SETI_UPLOADER_AVAILABLE and real_rmsExternal is not None:
        try:
            with open(log_path, "a") as log_file:
                log_file.write("\n--- Starting SetiUploader.py ---\n")
                log_file.flush()
                with contextlib.redirect_stdout(log_file), contextlib.redirect_stderr(log_file):
                    real_rmsExternal(captured_night_dir, archived_night_dir, config)
                log_file.write("--- SetiUploader.py finished ---\n")
        except Exception:
            with open(log_path, "a") as log_file:
                log_file.write("Error running SetiUploader.py:\n")
                traceback.print_exc(file=log_file)
            print("Error running SetiUploader.py:")
            traceback.print_exc()
    else:
        with open(log_path, "a") as log_file:
            log_file.write("SetiUploader not available; only logMeteorStats.sh was executed.\n")
        print("SetiUploader not available; only logMeteorStats.sh was executed.")


if __name__ == "__main__":
    # Optional manual test mode
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("captured", help="Captured night directory")
    parser.add_argument("archived", help="Archived night directory")
    parser.add_argument("-c", "--config", default=".config", help="Config path")
    args = parser.parse_args()

    config = cr.parse(args.config)
    rmsExternal(args.captured, args.archived, config)

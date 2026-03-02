#!/bin/bash

# To Gracefully stop RMS MultiCamLinux stations (StartCapture.sh) and exit.
# No update, no restart, no syslog logging.
#
# Code based on Ed Harman's GRMSUpdater and is for my own personal use.
# Ed's copyright listed below.

# This software is part of the Linux port of RMS
# Copyright (C) 2023  Ed Harman
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


#
# Usage:
#   ./GRMSShutdown.sh               # stop all running stations
#   ./GRMSShutdown.sh NZ0014 NZ002K # stop only these stations (if running)
#
# Options:
#   --timeout SECS   # default 600
#   --interval SECS  # default 5

set -Eeuo pipefail

# ------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/GRMSShutdown.log"

START_EPOCH=$(date -u +%s)
START_TIME_UTC=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

RESULT="graceful"

{
  echo "=================================================="
  echo "Shutdown script started at: $START_TIME_UTC"
} >> "$LOG_FILE"

TIMEOUT=600
INTERVAL=5

usage() {
  echo "Usage: $0 [--timeout SECS] [--interval SECS] [STATION ...]" >&2
}

# ------------------------------------------------------------
# regex_for() – match ONLY the StartCapture.sh argv for a station
# (same intent as in GRMSUpdater.sh) :contentReference[oaicite:1]{index=1}
# ------------------------------------------------------------
regex_for() {
  # station id must be a standalone argument following StartCapture.sh
  echo '^/bin/bash[[:space:]]+.*/StartCapture\.sh[[:space:]]+'"$1"'([[:space:]]|$)'
}

# Parse args
STATIONS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      TIMEOUT="$2"; shift 2;;
    --interval)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      INTERVAL="$2"; shift 2;;
    -h|--help)
      usage; exit 0;;
    --)
      shift; break;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 2;;
    *)
      STATIONS+=("$1"); shift;;
  esac
done

# If no station list provided, discover running stations from StartCapture.sh processes :contentReference[oaicite:2]{index=2}
if [[ ${#STATIONS[@]} -eq 0 ]]; then
  mapfile -t STATIONS < <(
    pgrep -f "Scripts/MultiCamLinux/StartCapture.sh" | while read -r pid; do
      cmdline=$(ps -p "$pid" -o args= 2>/dev/null || continue)
      if [[ "$cmdline" =~ Scripts/MultiCamLinux/StartCapture\.sh[[:space:]]+([[:alnum:]]{6}) ]]; then
        echo "${BASH_REMATCH[1]}"
      fi
    done | sort -u
  )
fi

if [[ ${#STATIONS[@]} -eq 0 ]]; then
  echo "No running RMS stations found."
  echo "Station list: (none)" >> "$LOG_FILE"
  RESULT="graceful"
  # fall through to end-of-script logging
else
  echo "Stopping ${#STATIONS[@]} station(s): ${STATIONS[*]}"
  echo "Station list: ${STATIONS[*]}" >> "$LOG_FILE"
fi

# Send SIGTERM to each station's StartCapture.sh interpreter line (graceful) :contentReference[oaicite:3]{index=3}
for station in "${STATIONS[@]}"; do
  pattern=$(regex_for "$station")
  if pkill -f -TERM -- "$pattern" 2>/dev/null; then
    echo "Sent SIGTERM to station $station"
  else
    echo "No matching processes for station $station (already stopped?)"
  fi
done

# Wait for clean shutdown :contentReference[oaicite:4]{index=4}
elapsed=0
while [[ $elapsed -lt $TIMEOUT ]]; do
  still_running=()
  for station in "${STATIONS[@]}"; do
    pattern=$(regex_for "$station")
    if pgrep -f -- "$pattern" >/dev/null 2>&1; then
      still_running+=("$station")
    fi
  done

  if [[ ${#still_running[@]} -eq 0 ]]; then
    echo "All stations stopped gracefully after ${elapsed}s."
    RESULT="graceful"
    break
  fi

  echo "Waiting: still running: ${still_running[*]} (${elapsed}s elapsed)"
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done

# Force kill leftovers :contentReference[oaicite:5]{index=5}
final_check=()
for station in "${STATIONS[@]}"; do
  pattern=$(regex_for "$station")
  if pgrep -f -- "$pattern" >/dev/null 2>&1; then
    final_check+=("$station")
  fi
done

if [[ ${#final_check[@]} -gt 0 ]]; then
  echo "Timeout reached. Force killing: ${final_check[*]}"
  RESULT="forced"
  for station in "${final_check[@]}"; do
    pattern=$(regex_for "$station")
    pkill -f -KILL -- "$pattern" 2>/dev/null || true
  done
  sleep 2
fi

END_EPOCH=$(date -u +%s)
END_TIME_UTC=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
ELAPSED=$((END_EPOCH - START_EPOCH))

{
  echo "Result: $RESULT"
  echo "Shutdown script finished at: $END_TIME_UTC"
  echo "Total runtime: ${ELAPSED} seconds"
} >> "$LOG_FILE"

echo "Shutdown script complete."
exit 0
#!/usr/bin/env python3

import argparse
import re
import zipfile
from pathlib import Path


TRIGGER_RE = re.compile(
    r"^(?P<intro>[^_]+)_"
    r"(?P<station>[^_]+)_"
    r"(?P<date>\d{8})_"
    r"(?P<time>\d{6}_\d+_\d+)"
    r"\.fits_maxpixel\.jpg$",
    re.IGNORECASE,
)

EVENT_RE = re.compile(
    r"^(?P<intro>[^_]+)_"
    r"(?P<station>[^_]+)_"
    r"(?P<date>\d{8})_"
    r"(?P<time>\d{6}_\d+_\d+)"
    r"(?P<suffix>.*)$",
    re.IGNORECASE,
)


def get_event_key(path: Path):
    match = EVENT_RE.match(path.name)
    if not match:
        return None

    return (
        match.group("station"),
        match.group("date"),
        match.group("time"),
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Find *.fits_maxpixel.jpg files and add each JPG plus all files "
            "with the same station/date/time to a ZIP archive."
        )
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Folder containing the files (default: current directory)",
    )
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()

    if not folder.is_dir():
        raise SystemExit(f"Error: folder does not exist: {folder}")

    output_folder = Path.cwd()

    all_files = [p for p in folder.iterdir() if p.is_file()]

    trigger_files = sorted(
        p for p in all_files
        if TRIGGER_RE.match(p.name)
    )

    if not trigger_files:
        print(f"No *.fits_maxpixel.jpg files found in {folder}")
        return

    archive_groups = {}

    for jpg_path in trigger_files:
        trigger = TRIGGER_RE.match(jpg_path.name)

        station = trigger.group("station")
        date = trigger.group("date")
        time_value = trigger.group("time")

        event_key = (station, date, time_value)

        matching_files = [
            path for path in all_files
            if get_event_key(path) == event_key
        ]

        archive_key = (station, date)
        archive_groups.setdefault(archive_key, set()).update(matching_files)

        print(f"\nTrigger: {jpg_path.name}")
        print(f"  Station: {station}")
        print(f"  Date:    {date}")
        print(f"  Time:    {time_value}")
        print(f"  Found {len(matching_files)} matching file(s):")

        for path in sorted(matching_files):
            print(f"    {path.name}")

    print()

    for (station, date), files in sorted(archive_groups.items()):
        archive_path = output_folder / f"{station}_{date}.zip"

        with zipfile.ZipFile(
            archive_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for path in sorted(files):
                archive.write(path, arcname=path.name)

        print(
            f"Created {archive_path.name} "
            f"containing {len(files)} file(s)"
        )


if __name__ == "__main__":
    main()

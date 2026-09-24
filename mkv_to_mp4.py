#!/usr/bin/env python3

import argparse
import subprocess
import sys
from pathlib import Path


def convert_mkv(mkv_file: Path, overwrite: bool = False) -> bool:
    """Convert one MKV file to MP4."""

    mp4_file = mkv_file.with_suffix(".mp4")

    if mp4_file.exists() and not overwrite:
        print(f"Skipping: {mp4_file.name} already exists")
        return True

    print(f"Converting: {mkv_file}")
    print(f"        to: {mp4_file}")

    command = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-i", str(mkv_file),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(mp4_file),
    ]

    try:
        result = subprocess.run(command)

        if result.returncode == 0:
            print(f"Done: {mp4_file.name}\n")
            return True

        print(f"ERROR converting: {mkv_file}\n")
        return False

    except FileNotFoundError:
        print("ERROR: FFmpeg was not found.")
        print("Please install FFmpeg and make sure 'ffmpeg' is in your PATH.")
        sys.exit(1)


def find_mkv_files(paths):
    """Return MKV files supplied directly or found in supplied folders."""

    files = []

    for item in paths:
        path = Path(item).expanduser()

        if path.is_file():
            if path.suffix.lower() == ".mkv":
                files.append(path)
            else:
                print(f"Ignoring non-MKV file: {path}")

        elif path.is_dir():
            found = sorted(
                p for p in path.iterdir()
                if p.is_file() and p.suffix.lower() == ".mkv"
            )
            files.extend(found)

        else:
            print(f"Not found: {path}")

    # Remove duplicates while retaining order
    unique_files = []
    seen = set()

    for file in files:
        resolved = file.resolve()

        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(file)

    return unique_files


def main():
    parser = argparse.ArgumentParser(
        description="Convert MKV video files to MP4 using FFmpeg."
    )

    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more MKV files and/or folders"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite existing MP4 files"
    )

    args = parser.parse_args()

    mkv_files = find_mkv_files(args.paths)

    if not mkv_files:
        print("No MKV files found.")
        return

    print(f"\nFound {len(mkv_files)} MKV file(s).\n")

    successful = 0
    failed = 0

    for number, mkv_file in enumerate(mkv_files, start=1):
        print(f"[{number}/{len(mkv_files)}]")

        if convert_mkv(mkv_file, args.force):
            successful += 1
        else:
            failed += 1

    print("=" * 50)
    print(f"Finished.")
    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")


if __name__ == "__main__":
    main()
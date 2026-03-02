import os
import re
import argparse
import subprocess
from pathlib import Path


def extract_datetime(filename):
    """
    Extracts datetime from patterns like: NZ005R_20251210_015938_video.mp4
    Returns sortable "YYYYMMDD_HHMMSS".
    """
    match = re.search(r"(\d{8}_\d{6})", filename)
    return match.group(1) if match else None


def main(folder):
    folder = Path(folder)
    mp4s = list(folder.glob("*.mp4"))

    if not mp4s:
        print("No MP4 files found.")
        return

    # Build list of (datetime, file)
    dated_files = []
    for f in mp4s:
        dt = extract_datetime(f.name)
        if dt:
            dated_files.append((dt, f))
        else:
            print(f"Skipping unrecognized filename: {f.name}")

    if not dated_files:
        print("No files with valid datetime patterns found.")
        return

    # Sort by datetime
    dated_files.sort(key=lambda x: x[0])

    # Create ffmpeg concat text file
    concat_path = folder / "concat_list.txt"
    with concat_path.open("w", encoding="utf-8") as f:
        for _, filepath in dated_files:
            f.write(f"file '{filepath.as_posix()}'\n")

    output_file = folder / "merged_output.mp4"

    cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_path),
        "-c", "copy",
        str(output_file)
    ]

    print("\nRunning ffmpeg...")
    print(" ".join(cmd))

    subprocess.run(cmd, check=True)

    print("\nDone!")
    print(f"Merged file created: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Concatenate MP4 files by datetime.")
    parser.add_argument("folder", help="Folder containing MP4 files")
    args = parser.parse_args()

    main(args.folder)
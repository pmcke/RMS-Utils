"""
extractBz2.py

Extracts all .tar.bz2 archives in a folder.

Usage:
    python extractBz2.py <input_folder> [output_folder] [--overwrite]

If output_folder is not provided, files are extracted into input_folder.

For each file in an archive, only the final folder and filename are
preserved. For example:

    some/path/NZ0014/file.txt

is extracted as:

    <output_folder>/NZ0014/file.txt

By default, if the destination folder for an archive already exists,
the entire archive is skipped. Use --overwrite to extract it again.
"""

import argparse
import os
import tarfile


def extract_bz2_files(input_folder, output_folder=None, overwrite=False):
    """Extract all .tar.bz2 files found directly inside input_folder."""

    if not os.path.isdir(input_folder):
        print(f"The input folder does not exist: {input_folder}")
        return

    if output_folder is None:
        output_folder = input_folder

    os.makedirs(output_folder, exist_ok=True)

    archive_names = sorted(
        name
        for name in os.listdir(input_folder)
        if name.lower().endswith(".tar.bz2")
    )

    if not archive_names:
        print(f"No .tar.bz2 archives found in: {input_folder}")
        return

    for file_name in archive_names:
        file_path = os.path.join(input_folder, file_name)

        try:
            with tarfile.open(file_path, "r:bz2") as tar:
                members = tar.getmembers()

                # Find the first actual file in the archive.
                # The first member may only be a directory entry.
                first_file = next(
                    (member for member in members if member.isfile()),
                    None,
                )

                if first_file is None:
                    print(f"Skipping {file_name}: archive contains no files.")
                    continue

                first_parts = (
                    first_file.name.strip("/\\")
                    .replace("\\", "/")
                    .split("/")
                )

                # Determine the folder that this archive will create
                # in the destination directory.
                if len(first_parts) > 1:
                    destination_folder_name = first_parts[-2]
                    destination_folder = os.path.join(
                        output_folder,
                        destination_folder_name,
                    )

                    # Skip the whole archive if its destination folder exists.
                    if os.path.isdir(destination_folder) and not overwrite:
                        print(
                            f"Skipping {file_name}: destination folder already "
                            f"exists: {destination_folder}"
                        )
                        continue

                extracted_count = 0

                for member in members:
                    if not member.isfile():
                        continue

                    parts = (
                        member.name.strip("/\\")
                        .replace("\\", "/")
                        .split("/")
                    )

                    if len(parts) > 1:
                        new_name = os.path.join(parts[-2], parts[-1])
                    else:
                        new_name = parts[-1]

                    destination_path = os.path.join(output_folder, new_name)
                    destination_directory = os.path.dirname(destination_path)

                    if destination_directory:
                        os.makedirs(destination_directory, exist_ok=True)

                    # Replace the full archive path with the shortened path.
                    member.name = new_name
                    tar.extract(member, path=output_folder)
                    extracted_count += 1

                print(
                    f"Extracted {file_name} to {output_folder} "
                    f"({extracted_count} files)"
                )

        except (tarfile.TarError, OSError) as error:
            print(f"Failed to extract {file_name}: {error}")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Extract all .tar.bz2 archives in a folder."
    )

    parser.add_argument(
        "input_folder",
        help="Folder containing the .tar.bz2 archives.",
    )

    parser.add_argument(
        "output_folder",
        nargs="?",
        default=None,
        help="Destination folder. Defaults to the input folder.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Extract archives even when their destination folders already exist.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    extract_bz2_files(
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        overwrite=args.overwrite,
    )
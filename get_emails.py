#!/usr/bin/env python3

import argparse
from pathlib import Path


def extract_email_addresses(folder_path):
    folder = Path(folder_path)

    if not folder.is_dir():
        print(f"Error: '{folder}' is not a valid folder.")
        return

    output_file = folder / "email_addresses.txt"
    email_addresses = []

    for file_path in folder.iterdir():
        # Only process files
        if not file_path.is_file():
            continue

        # Don't process our own output file
        if file_path == output_file:
            continue

        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("To:"):
                        email_address = line[3:].strip()

                        if email_address:
                            email_addresses.append(email_address)

        except (OSError, UnicodeError) as e:
            print(f"Could not read {file_path.name}: {e}")

    with output_file.open("w", encoding="utf-8") as f:
        for email_address in email_addresses:
            f.write(email_address + ";\n")

    print(f"Found {len(email_addresses)} email address(es).")
    print(f"Saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract email addresses from lines beginning with 'To:'."
    )

    parser.add_argument(
        "folder",
        help="Folder containing the files to examine"
    )

    args = parser.parse_args()

    extract_email_addresses(args.folder)


if __name__ == "__main__":
    main()

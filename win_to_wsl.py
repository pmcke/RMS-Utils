import sys
import subprocess
from pathlib import PureWindowsPath

def windows_to_wsl(path):
    p = PureWindowsPath(path)
    drive = p.drive.rstrip(':').lower()
    rest = "/".join(p.parts[1:])
    return f"/mnt/{drive}/{rest}"

def copy_to_clipboard_windows(text):
    subprocess.run(
        ["clip"],
        input=text,
        text=True,
        shell=True
    )

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python win_to_wsl.py "C:\\path\\to\\folder"')
        sys.exit(1)

    result = windows_to_wsl(sys.argv[1])
    print(result)
    copy_to_clipboard_windows(result)

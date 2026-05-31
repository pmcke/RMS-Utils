
# Before using the user needs to run the following:

#  sed -i 's/\r$//' install_rustdesk.sh
#  chmod +x install_rustdesk.sh
#  ./install_rustdesk.sh <ID> <password>



#!/usr/bin/env bash
set -euo pipefail

# Default settings used if install_rustdesk.ini is absent
ID_SERVER=""
RELAY_SERVER=""
KEY=""
ENABLE_REMOTE_CONFIGURATION_MODIFICATION="off"

INI_FILE="./install_rustdesk.ini"

if [ "$EUID" -eq 0 ]; then
    echo "Please run this script as a normal user, not with sudo."
    exit 1
fi

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <STATION_NAME> <RUSTDESK_PASSWORD>"
    echo "Example: $0 NZ0014 'your-password'"
    exit 1
fi

STATION="$1"
RD_PASSWORD="$2"

echo "Checking sudo access..."
sudo -v

echo "This software will allow remote users to access this machine. Do you want to continue (Y/N)"
read -r ANSWER
case "$ANSWER" in
    Y|y) ;;
    *) echo "Installation cancelled."; exit 0 ;;
esac

if [ -f "$INI_FILE" ]; then
    echo "Reading settings from $INI_FILE..."

    while IFS='=' read -r key value; do
        key="$(echo "$key" | xargs)"
        value="$(echo "$value" | sed "s/^['\"]//; s/['\"]$//" | xargs)"

        case "$key" in
            ID_SERVER) ID_SERVER="$value" ;;
            RELAY_SERVER) RELAY_SERVER="$value" ;;
            KEY) KEY="$value" ;;
            ENABLE_REMOTE_CONFIGURATION_MODIFICATION)
                ENABLE_REMOTE_CONFIGURATION_MODIFICATION="$value"
                ;;
        esac
    done < "$INI_FILE"
else
    echo "No install_rustdesk.ini found; using default settings."
fi

case "${ENABLE_REMOTE_CONFIGURATION_MODIFICATION,,}" in
    on|yes|true|1|y)
        ALLOW_REMOTE_CONFIG_MODIFICATION="Y"
        ;;
    *)
        ALLOW_REMOTE_CONFIG_MODIFICATION="N"
        ;;
esac

if ! command -v curl >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y curl ca-certificates python3
fi

ARCH="$(dpkg --print-architecture)"

case "$ARCH" in
    amd64)
        WANT_ARCH_REGEX='(x86_64|amd64)'
        ;;
    arm64)
        WANT_ARCH_REGEX='(aarch64|arm64)'
        ;;
    armhf)
        WANT_ARCH_REGEX='(armv7|armhf)'
        ;;
    *)
        echo "Unsupported package architecture: $ARCH"
        exit 1
        ;;
esac

echo "Detected package architecture: $ARCH"

if [ -f /etc/debian_version ]; then
    PKG_EXT="deb"
    INSTALL_CMD="sudo apt install -y"
elif [ -f /etc/redhat-release ]; then
    PKG_EXT="rpm"
    INSTALL_CMD="sudo yum localinstall -y"
elif command -v pacman >/dev/null 2>&1; then
    PKG_EXT="pkg.tar.zst"
    INSTALL_CMD="sudo pacman -U --noconfirm"
else
    echo "Unsupported Linux distribution for automatic install."
    exit 1
fi

TMPDIR="$(mktemp -d)"
cd "$TMPDIR"

echo "Finding latest RustDesk release..."
ASSET_URL="$(
python3 - <<PY
import json, re, urllib.request

arch_re = re.compile(r"$WANT_ARCH_REGEX", re.I)
ext = "$PKG_EXT"

data = json.load(
    urllib.request.urlopen("https://api.github.com/repos/rustdesk/rustdesk/releases/latest")
)

for asset in data["assets"]:
    name = asset["name"]
    if name.endswith(ext) and arch_re.search(name):
        if "suse" not in name.lower():
            print(asset["browser_download_url"])
            break
PY
)"

if [ -z "$ASSET_URL" ]; then
    echo "Could not find a RustDesk $PKG_EXT package for architecture $ARCH."
    exit 1
fi

PKG_FILE="$(basename "$ASSET_URL")"
echo "Downloading $PKG_FILE..."
curl -L -o "$PKG_FILE" "$ASSET_URL"

echo "Installing RustDesk..."
$INSTALL_CMD "./$PKG_FILE"

USER_CONFIG_DIR="$HOME/.config/rustdesk"
ROOT_CONFIG_DIR="/root/.config/rustdesk"

mkdir -p "$USER_CONFIG_DIR"
sudo mkdir -p "$ROOT_CONFIG_DIR"

echo "Writing RustDesk server settings..."

cat > "$USER_CONFIG_DIR/RustDesk2.toml" <<EOF
rendezvous_server = '$ID_SERVER'
nat_type = 1
serial = 0

[options]
custom-rendezvous-server = '$ID_SERVER'
relay-server = '$RELAY_SERVER'
key = '$KEY'
allow-remote-config-modification = '$ALLOW_REMOTE_CONFIG_MODIFICATION'
EOF

sudo cp "$USER_CONFIG_DIR/RustDesk2.toml" "$ROOT_CONFIG_DIR/RustDesk2.toml"

echo "Starting RustDesk service so it creates RustDesk.toml..."
sudo systemctl enable --now rustdesk
sleep 10

echo "Stopping RustDesk service while applying station ID..."
sudo systemctl stop rustdesk 2>/dev/null || true

ROOT_TOML="$ROOT_CONFIG_DIR/RustDesk.toml"
sudo touch "$ROOT_TOML"

echo "Setting RustDesk ID to $STATION in $ROOT_TOML..."

sudo python3 - "$ROOT_TOML" "$STATION" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
station = sys.argv[2]

text = path.read_text()
lines = text.splitlines()

done = False
new_lines = []

for line in lines:
    stripped = line.strip()
    if stripped.startswith("enc_id =") or stripped.startswith("id ="):
        new_lines.append(f"id = '{station}'")
        done = True
    else:
        new_lines.append(line)

if not done:
    new_lines.insert(0, f"id = '{station}'")

path.write_text("\n".join(new_lines) + "\n")
PY

echo "Starting RustDesk service..."
sudo systemctl start rustdesk

echo "Waiting for RustDesk service..."
sleep 10

echo "Setting RustDesk permanent password..."
sudo rustdesk --password "$RD_PASSWORD"

echo "RustDesk install/config complete."
echo "Station: $STATION"
echo "ID server: $ID_SERVER"
echo "Relay server: $RELAY_SERVER"
echo "Remote configuration modification: $ENABLE_REMOTE_CONFIGURATION_MODIFICATION"
echo "RustDesk ID:"
sudo rustdesk --get-id || true

echo
echo "RustDesk may re-encrypt the station ID as enc_id after startup."
echo "If the RustDesk GUI shows the station name, the ID setting worked."

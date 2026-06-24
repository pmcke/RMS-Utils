
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

CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-unknown}")"
OS_ID="$(. /etc/os-release && echo "${ID:-unknown}")"

if [ "$CODENAME" = "buster" ]; then
    if grep -q "raspbian.raspberrypi.org" /etc/apt/sources.list; then
        echo
        echo "WARNING: Buster may require legacy repository URLs."
        echo "If installation fails with 404 errors, change:"
        echo "  raspbian.raspberrypi.org"
        echo "to:"
        echo "  legacy.raspbian.org"
        echo
    fi
fi

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

# RustDesk's command-line option setter is needed on some Ubuntu builds
# because the service rewrites RustDesk2.toml at startup.  Keep the
# original TOML method for Raspberry Pi / Raspberry Pi OS, where it is
# already proven to work.
add_default_port_if_missing() {
    local value="$1"
    local port="$2"

    if [ -z "$value" ]; then
        echo ""
    elif [[ "$value" == *:* ]]; then
        echo "$value"
    else
        echo "${value}:${port}"
    fi
}

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

if [ "$OS_ID" = "ubuntu" ]; then
    echo "Applying RustDesk server settings using rustdesk --option for Ubuntu..."

    UBUNTU_ID_SERVER="$(add_default_port_if_missing "$ID_SERVER" "21116")"
    UBUNTU_RELAY_SERVER="$(add_default_port_if_missing "$RELAY_SERVER" "21117")"

    if [ -n "$UBUNTU_ID_SERVER" ]; then
        sudo rustdesk --option custom-rendezvous-server "$UBUNTU_ID_SERVER" || true
    fi

    if [ -n "$UBUNTU_RELAY_SERVER" ]; then
        sudo rustdesk --option relay-server "$UBUNTU_RELAY_SERVER" || true
    fi

    if [ -n "$KEY" ]; then
        sudo rustdesk --option key "$KEY" || true
    fi

    sudo rustdesk --option allow-remote-config-modification "$ALLOW_REMOTE_CONFIG_MODIFICATION" || true
fi

echo "Starting RustDesk service so it creates RustDesk.toml..."
sudo systemctl enable --now rustdesk
sleep 20

echo "Stopping RustDesk service while applying station ID..."
sudo systemctl stop rustdesk 2>/dev/null || true

if [ "$OS_ID" = "ubuntu" ]; then
    echo "Re-applying RustDesk server settings using rustdesk --option for Ubuntu..."

    UBUNTU_ID_SERVER="$(add_default_port_if_missing "$ID_SERVER" "21116")"
    UBUNTU_RELAY_SERVER="$(add_default_port_if_missing "$RELAY_SERVER" "21117")"

    if [ -n "$UBUNTU_ID_SERVER" ]; then
        sudo rustdesk --option custom-rendezvous-server "$UBUNTU_ID_SERVER" || true
    fi

    if [ -n "$UBUNTU_RELAY_SERVER" ]; then
        sudo rustdesk --option relay-server "$UBUNTU_RELAY_SERVER" || true
    fi

    if [ -n "$KEY" ]; then
        sudo rustdesk --option key "$KEY" || true
    fi

    sudo rustdesk --option allow-remote-config-modification "$ALLOW_REMOTE_CONFIG_MODIFICATION" || true
fi

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
sleep 20

echo "Setting RustDesk permanent password..."

PASSWORD_SET=0
for attempt in 1 2 3 4 5; do
    if sudo rustdesk --password "$RD_PASSWORD"; then
        PASSWORD_SET=1
        break
    fi

    echo "Password set failed; retrying in 5 seconds..."
    sleep 5
done

if [ "$PASSWORD_SET" -ne 1 ]; then
    echo "WARNING: Unable to set RustDesk password automatically."
    echo "You can set it manually with:"
    echo "sudo rustdesk --password '<password>'"
fi

echo "RustDesk install/config complete."
echo "Station: $STATION"
echo "ID server: $ID_SERVER"
echo "Relay server: $RELAY_SERVER"
echo "Remote configuration modification: $ENABLE_REMOTE_CONFIGURATION_MODIFICATION"
if [ "$OS_ID" = "ubuntu" ]; then
    echo "Ubuntu option ID server: ${UBUNTU_ID_SERVER:-}"
    echo "Ubuntu option relay server: ${UBUNTU_RELAY_SERVER:-}"
fi
echo "RustDesk ID:"
sudo rustdesk --get-id || true

echo
echo "RustDesk may re-encrypt the station ID as enc_id after startup."
echo "If the RustDesk GUI shows the station name, the ID setting worked."

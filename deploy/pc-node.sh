#!/usr/bin/env bash
# Connects this Windows PC to OpenClaw as a node, so commands from the Watch can act on Windows.
#
#   bash deploy/pc-node.sh            # set up, or report the node that is already connected
#   bash deploy/pc-node.sh --replace  # also replace an OpenClaw node service Ceviz did not create
#
# WSL only: elsewhere the Gateway runs on the computer itself and OpenClaw's exec already acts
# on it. deploy/install.sh runs this by default (WATCH_CEVIZ_PC_NODE_SETUP=0 skips it).
#
# The Gateway mints a single-use, limited setup code (no admin access); Windows pairs with it and
# then uses its own device token. The Gateway token never leaves WSL. Commands then run on
# Windows without asking for approval, as OpenClaw's exec does inside WSL (deploy/README.md).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="${WATCH_CEVIZ_PC_NODE_NAME:-Ceviz PC}"
REPLACE=()
[ "${1:-}" = --replace ] && REPLACE=(-Replace)

if ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "==> PC dugumu gerekmiyor: OpenClaw bu bilgisayarda calisiyor, komutlar dogrudan burada calisir"
  exit 0
fi
# Run OpenClaw as the installed helper does (its PATH and OPENCLAW_HOME): under WSL a shell
# without ~/.local/bin finds the Windows `openclaw`, which belongs to another setup.
if SERVICE_ENV="$(python3 - "$SCRIPT_DIR" 2>/dev/null <<'PY'
import shlex, sys
sys.path.insert(0, sys.argv[1])
import plan
_, runtime = plan.ceviz_service()
for key, value in runtime.items():
    # In front of this shell's PATH, which still finds powershell.exe and wslpath.
    print(f'export {key}={shlex.quote(value)}' + (':"$PATH"' if key == "PATH" else ""))
PY
)"; then
  eval "$SERVICE_ENV"
fi
for tool in openclaw powershell.exe wslpath python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "!! PC dugumu icin $tool gerekli." >&2; exit 1; }
done

# The node with this device id (or, without one, any connected Windows node that can run
# commands): "<connected 0|1> <system.run 0|1> <name>".
node_state() {
  openclaw nodes status --json 2>/dev/null | python3 -c '
import json, sys
device = sys.argv[1]
try:
    nodes = json.load(sys.stdin).get("nodes", [])
except ValueError:
    nodes = []
for node in nodes:
    runs = "system.run" in (node.get("commands") or [])
    if node.get("nodeId") == device if device else (node.get("platform") == "windows" and node.get("connected") and runs):
        print(int(bool(node.get("connected"))), int(runs), node.get("displayName") or "")
        break
' "${1:-}"
}

# Bootstrap pairing normally approves the device and its commands at once. Should the Gateway
# still ask, approve only requests from the device this run paired.
approve_own_requests() {
  local device="$1" request
  for request in $(openclaw devices list --json 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
for item in data.get("pending", []) if isinstance(data, dict) else []:
    if item.get("deviceId") == sys.argv[1]:
        print(item.get("requestId") or item.get("id") or "")
' "$device"); do
    openclaw devices approve "$request" >/dev/null 2>&1 || true
  done
  for request in $(openclaw nodes pending --json 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except ValueError:
    data = []
for item in data if isinstance(data, list) else data.get("pending", []):
    if item.get("nodeId") == sys.argv[1] or item.get("deviceId") == sys.argv[1]:
        print(item.get("requestId") or item.get("id") or "")
' "$device"); do
    openclaw nodes approve "$request" >/dev/null 2>&1 || true
  done
}

# The helper tells the agent which node is the user's PC.
remember_node() {
  local dropin="$HOME/.config/systemd/user/watch-ceviz-backend.service.d"
  if command -v systemctl >/dev/null 2>&1 && systemctl --user cat watch-ceviz-backend >/dev/null 2>&1; then
    mkdir -p "$dropin"
    printf '[Service]\nEnvironment="WATCH_CEVIZ_PC_NODE=%s"\n' "$1" > "$dropin/pc-node.conf"
    systemctl --user daemon-reload
    systemctl --user try-restart watch-ceviz-backend || true
  fi
}

read -r connected runs existing < <(node_state "") || true
if [ "${connected:-0}" = 1 ]; then
  echo "==> PC dugumu zaten bagli: $existing (komutlar Windows'ta calisabilir)"
  remember_node "$existing"
  exit 0
fi

PORT="$(openclaw config get gateway.port 2>/dev/null | tr -d '[:space:]' || true)"
[[ "$PORT" =~ ^[0-9]{1,5}$ ]] || PORT=18789
VERSION="$(openclaw --version 2>/dev/null | sed -n 's/^OpenClaw \([0-9][0-9A-Za-z.+-]*\).*/\1/p' | head -1 || true)"
[ -n "$VERSION" ] || { echo "!! OpenClaw surumu okunamadi." >&2; exit 1; }
# Windows reaches the Gateway in WSL on localhost; the code carries that address.
CODE="$(openclaw qr --setup-code-only --limited --no-ascii --url "ws://127.0.0.1:$PORT" 2>/dev/null \
  | tail -1 | tr -d '[:space:]' || true)"
[ -n "$CODE" ] || { echo "!! Gateway bir kurulum kodu uretmedi (openclaw qr)." >&2; exit 1; }

echo "==> Bu PC OpenClaw'a dugum olarak baglaniyor: $NAME (OpenClaw $VERSION, ayri klasorde)"
STATUS=0
OUTPUT="$(printf '%s' "$CODE" | powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass \
  -File "$(wslpath -w "$SCRIPT_DIR/windows/install-pc-node.ps1")" -Version "$VERSION" -DisplayName "$NAME" \
  ${REPLACE[@]+"${REPLACE[@]}"} 2>&1 | tr -d '\r')" || STATUS=$?
CODE=""
printf '%s\n' "$OUTPUT" | grep -v '^CEVIZ_PC_NODE_' || true
DEVICE="$(printf '%s\n' "$OUTPUT" | sed -n 's/^CEVIZ_PC_NODE_ID=\([0-9a-f]\{64\}\)$/\1/p' | tail -1)"
case "$STATUS" in
  0) ;;
  4) echo "!! Windows'ta Ceviz'in kurmadigi bir OpenClaw dugum servisi var:" \
          "$(printf '%s\n' "$OUTPUT" | sed -n 's/^CEVIZ_PC_NODE_FOREIGN=//p')" >&2
     echo "   Hicbir sey degistirilmedi. Yerine Ceviz'inkini kurmak icin: bash deploy/pc-node.sh --replace" >&2
     exit 2 ;;
  *) echo "!! PC dugumu kurulamadi: $(printf '%s\n' "$OUTPUT" | sed -n 's/^CEVIZ_PC_NODE_ERROR=//p')" >&2
     exit 2 ;;
esac
[ -n "$DEVICE" ] || { echo "!! Dugum kimligi okunamadi." >&2; exit 2; }

for _ in $(seq 1 30); do
  approve_own_requests "$DEVICE"
  read -r connected runs _name < <(node_state "$DEVICE") || true
  if [ "${connected:-0}" = 1 ] && [ "${runs:-0}" = 1 ]; then
    remember_node "$NAME"
    echo "==> PC dugumu bagli: $NAME. Saatten verilen bilgisayar komutlari Windows'ta calisir."
    exit 0
  fi
  sleep 2
done
echo "!! Dugum kuruldu ama 60 saniyede baglanmadi ya da komut calistiramiyor; 'openclaw nodes status' ile bak." >&2
exit 2

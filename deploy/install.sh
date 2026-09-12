#!/usr/bin/env bash
# Watch Ceviz backend — tek komutluk kurulum.
#
#   bash deploy/install.sh
#
# Yaptiklari:
#   - Python venv olusturur, bagimliliklari kurar (GPU varsa CUDA lib'leri de)
#   - Erisim token'i uretir
#   - systemd --user servisini yazar ve baslatir (yoksa nohup fallback)
#   - Tailscale varsa backend'i tailnet'e /ceviz olarak yayinlar
#   - Telefonda okutacagin QR + pairing bilgisini basar
#
# Ceviz repo kok dizininde calistirilabilir.
set -euo pipefail

# --- Repo kokunu bul (bu script deploy/ altinda) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"          # Ceviz repo root
cd "$APP_DIR"

# Installation is not an update: re-running it used to replace the service's
# custom environment and did not reliably restart an already-active process.
# Refuse before pip, token, service or network changes; update.py owns upgrades.
if [ -e "$APP_DIR/.auth-token" ] || [ -L "$APP_DIR/.auth-token" ] || \
   { command -v systemctl >/dev/null 2>&1 && \
     [ "$(systemctl --user show watch-ceviz-backend.service -p LoadState --value 2>/dev/null)" = loaded ]; }; then
  echo "!! Existing Ceviz installation detected. No settings or services changed." >&2
  echo "   Follow the existing-installation update instructions in deploy/README.md." >&2
  exit 1
fi

PORT="${WATCH_CEVIZ_PORT:-8080}"
if [[ ! "$PORT" =~ ^[0-9]{1,5}$ ]] || (( 10#$PORT < 1 || 10#$PORT > 65535 )); then
  echo "!! WATCH_CEVIZ_PORT must be a TCP port from 1 to 65535." >&2
  exit 1
fi
NETWORK_MODE="${WATCH_CEVIZ_NETWORK_MODE:-auto}"
VENV="$APP_DIR/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

echo "==> Watch Ceviz kurulumu: $APP_DIR"

# --- 0) OpenClaw var mi? Backend onu calistiracak. ---
if command -v openclaw >/dev/null 2>&1; then
  echo "==> OpenClaw bulundu: $(command -v openclaw)"
else
  echo "!!  UYARI: 'openclaw' PATH'te bulunamadi."
  echo "    Watch Ceviz komutlari OpenClaw CLI'ini calistirir; kurulum devam"
  echo "    edecek ama komutlar 'OpenClaw CLI bulunamadi' hatasi verecek."
  echo "    OpenClaw'i kur (https://openclaw.ai) ya da servis dosyasindaki"
  echo "    PATH degiskenine openclaw'in dizinini ekle."
fi

# --- 1) venv + bagimliliklar ---
INSTALL_PY=python3
[ -x "$PY" ] && INSTALL_PY="$PY"
if ! "$INSTALL_PY" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "!! Python 3.11 or newer is required by the pinned dependencies. No packages or settings changed." >&2
  exit 1
fi
if [[ "$PATH" == *$'\n'* || "$PATH" == *$'\r'* ]]; then
  echo "!! PATH contains a line break; choose a normal OpenClaw CLI path before installing." >&2
  exit 1
fi
# systemd does not inherit the installing shell's PATH. Preserve it explicitly,
# including WSL paths with spaces; escape unit quoting and %-specifiers.
SYSTEMD_PATH="${PATH//\\/\\\\}"
SYSTEMD_PATH="${SYSTEMD_PATH//\"/\\\"}"
SYSTEMD_PATH="${SYSTEMD_PATH//%/%%}"
if [ ! -x "$PY" ]; then
  echo "==> Python venv olusturuluyor"
  python3 -m venv "$VENV"
fi
"$PIP" install -q --upgrade pip
"$PIP" install -q -r "$SCRIPT_DIR/requirements.txt"

# --- 2) GPU tespiti + CUDA lib'leri ---
WHISPER_MODEL="${WATCH_CEVIZ_WHISPER_MODEL:-small}"
LD_LIBS=""
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  echo "==> GPU bulundu — CUDA kutuphaneleri kuruluyor (large-v3 icin)"
  "$PIP" install -q nvidia-cublas-cu12 nvidia-cudnn-cu12
  SITE="$("$PY" -c 'import site; print(site.getsitepackages()[0])')"
  LD_LIBS="$SITE/nvidia/cublas/lib:$SITE/nvidia/cudnn/lib"
  WHISPER_MODEL="${WATCH_CEVIZ_WHISPER_MODEL:-large-v3}"
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet ollama 2>/dev/null; then
    echo "!!  UYARI: Ollama ve Ceviz Whisper ayni WSL GPU'sunu kullanabilir."
    echo "    Bellek baskisi gorursen Ollama otomatik baslatmasini kapat veya"
    echo "    WATCH_CEVIZ_WHISPER_MODEL=small ile Ceviz'i yeniden kur."
  fi
else
  echo "==> GPU yok — CPU modu (model=$WHISPER_MODEL)"
fi

# --- 3) Token ---
TOKEN_FILE="$APP_DIR/.auth-token"
if [ -f "$TOKEN_FILE" ]; then
  TOKEN="$(cat "$TOKEN_FILE")"
  echo "==> Mevcut token kullaniliyor ($TOKEN_FILE)"
else
  TOKEN="$(openssl rand -hex 24)"
  ( umask 077; printf '%s' "$TOKEN" > "$TOKEN_FILE" )
  echo "==> Yeni token uretildi ($TOKEN_FILE)"
fi

# --- 4) systemd --user servisi ---
LANG_ENV="${WATCH_CEVIZ_WHISPER_LANGUAGE:-tr}"
AGENT_ENV="${OPENCLAW_WATCH_AGENT:-main}"
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  {
    echo "[Unit]"
    echo "Description=Watch Ceviz Backend (PTT->Summary, local Whisper STT)"
    echo "After=network-online.target"
    echo ""
    echo "[Service]"
    echo "Type=simple"
    echo "WorkingDirectory=$APP_DIR"
    echo "Environment=HOME=$HOME"
    printf 'Environment="PATH=%s"\n' "$SYSTEMD_PATH"
    echo "Environment=WATCH_CEVIZ_STT_ENGINE=auto"
    echo "Environment=WATCH_CEVIZ_WHISPER_MODEL=$WHISPER_MODEL"
    echo "Environment=WATCH_CEVIZ_WHISPER_LANGUAGE=$LANG_ENV"
    echo "Environment=OPENCLAW_WATCH_AGENT=$AGENT_ENV"
    echo "Environment=WATCH_CEVIZ_AUTH_TOKEN=$TOKEN"
    [ -n "$LD_LIBS" ] && echo "Environment=LD_LIBRARY_PATH=$LD_LIBS"
    echo "ExecStart=$PY $APP_DIR/backend/main.py $PORT"
    echo "Restart=on-failure"
    echo "RestartSec=5"
    echo ""
    echo "[Install]"
    echo "WantedBy=default.target"
  } > "$UNIT_DIR/watch-ceviz-backend.service"
  systemctl --user daemon-reload
  systemctl --user enable --now watch-ceviz-backend >/dev/null
  command -v loginctl >/dev/null 2>&1 && loginctl enable-linger "$(whoami)" >/dev/null 2>&1 || true
  echo "==> Servis calisiyor (systemctl --user status watch-ceviz-backend)"
else
  echo "==> systemd yok — nohup ile baslatiliyor"
  LD_LIBRARY_PATH="$LD_LIBS" WATCH_CEVIZ_AUTH_TOKEN="$TOKEN" \
    WATCH_CEVIZ_WHISPER_MODEL="$WHISPER_MODEL" WATCH_CEVIZ_WHISPER_LANGUAGE="$LANG_ENV" \
    WATCH_CEVIZ_STT_ENGINE=auto OPENCLAW_WATCH_AGENT="$AGENT_ENV" \
    nohup "$PY" "$APP_DIR/backend/main.py" "$PORT" > "$APP_DIR/backend.log" 2>&1 &
fi

# --- 5) Tailscale yayini + URL ---
IS_WSL=0
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1
if [ "$IS_WSL" = 1 ]; then
  if ! command -v powershell.exe >/dev/null 2>&1 || [ -z "${WSL_DISTRO_NAME:-}" ]; then
    echo "!! Windows PowerShell and WSL_DISTRO_NAME are required for persistent WSL availability." >&2
    echo "   The backend may stop when this terminal closes; see deploy/README.md." >&2
    exit 1
  fi
  LIFETIME_INSTALLER="$(wslpath -w "$SCRIPT_DIR/windows/install-wsl-lifetime.ps1")"
  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$LIFETIME_INSTALLER" -Distro "$WSL_DISTRO_NAME"
fi
WINDOWS_TS=0
if [ "$IS_WSL" = 1 ] && command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command 'if (Get-Command tailscale -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }' >/dev/null 2>&1 && WINDOWS_TS=1 || true
fi
if [ "$NETWORK_MODE" = auto ] && [ -t 0 ]; then
  echo "==> Baglanti yontemi: 1) Tailscale (onerilen)  2) Ayni Wi-Fi / Windows relay  3) Manuel"
  read -r -p "Secim [1]: " choice
  case "${choice:-1}" in 1) NETWORK_MODE=tailscale;; 2) NETWORK_MODE=relay;; 3) NETWORK_MODE=manual;; esac
fi
if [ "$NETWORK_MODE" = auto ]; then
  if command -v tailscale >/dev/null 2>&1 || [ "$WINDOWS_TS" = 1 ]; then NETWORK_MODE=tailscale
  elif [ "$IS_WSL" = 1 ]; then NETWORK_MODE=relay
  else NETWORK_MODE=manual; fi
fi
install_windows_relay() {
  local installer output relay_url
  if ! command -v powershell.exe >/dev/null 2>&1; then
    echo "!!  HATA: Windows PowerShell bulunamadi; relay kurulamadi." >&2
    return 1
  fi
  installer="$(wslpath -w "$SCRIPT_DIR/windows/install-relay.ps1")"
  if ! output="$(powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$installer" -Port "$PORT" \
      -Distro "$WSL_DISTRO_NAME" 2>&1 | tr -d '\r')"; then
    printf '%s\n' "$output" >&2
    echo "!!  HATA: Windows relay kurulumu basarisiz oldu." >&2
    return 1
  fi
  printf '%s\n' "$output" >&2
  relay_url="$(printf '%s\n' "$output" | sed -n 's/^CEVIZ_RELAY_URL=//p' | tail -1)"
  if [ -z "$relay_url" ]; then
    echo "!!  HATA: Relay kurulumu bir CEVIZ_RELAY_URL dondurmedi." >&2
    return 1
  fi
  printf '%s\n' "$relay_url"
}
# Tailscale yoksa bile kullanilabilir bir adres uret: yerel ag IP'si.
# Minimal sistemlerde `ip`/`hostname` bulunmayabilir — hicbiri kurulumu
# durdurmamali, en kotu ihtimalle yer tutucu adres basariz.
LAN_IP=""
if command -v ip >/dev/null 2>&1; then
  LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1 || true)"
fi
if [ -z "$LAN_IP" ] && command -v hostname >/dev/null 2>&1; then
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
BASE_URL="http://${LAN_IP:-<bu-makinenin-adresi>}:$PORT"
PAIRING_METHOD=manual
if [ "$NETWORK_MODE" = tailscale ] && command -v tailscale >/dev/null 2>&1; then
  tailscale serve --bg --set-path=/ceviz "http://127.0.0.1:$PORT" >/dev/null 2>&1 || \
    tailscale serve --bg --https=443 --set-path /ceviz "http://127.0.0.1:$PORT" >/dev/null 2>&1 || true
  TS_HOST="$(tailscale status --json 2>/dev/null | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("Self",{}).get("DNSName","").rstrip("."))' 2>/dev/null || true)"
  [ -n "$TS_HOST" ] && BASE_URL="https://$TS_HOST/ceviz"
  PAIRING_METHOD=tailscale
  echo "==> Tailscale serve: $BASE_URL"
elif [ "$NETWORK_MODE" = tailscale ] && [ "$WINDOWS_TS" = 1 ]; then
  # WSL localhost forwarding is independent of a LAN address and firewall.
  # Prove this exact backend is reachable before publishing its private route.
  if ! printf '%s' "$TOKEN" | powershell.exe -NoProfile -NonInteractive -Command "
    \$ErrorActionPreference='Stop'
    try {
      \$token=[Console]::In.ReadToEnd()
      \$features=Invoke-RestMethod -Uri 'http://127.0.0.1:$PORT/api/v1/capabilities' -TimeoutSec 5 -Headers @{Authorization=('Bearer '+\$token)}
      if (\$features.conversations_v1 -ne \$true) { exit 1 }
    } catch { exit 1 }" >/dev/null 2>&1; then
    echo "!! Windows cannot reach this Ceviz backend on localhost:$PORT. No LAN relay or firewall rule was created." >&2
    echo "   Use the WSL localhost-forwarding repair guidance in deploy/README.md." >&2
    exit 1
  fi
  powershell.exe -NoProfile -NonInteractive -Command "tailscale serve --bg --set-path=/ceviz http://127.0.0.1:$PORT; exit \$LASTEXITCODE" >/dev/null
  TS_HOST="$(powershell.exe -NoProfile -NonInteractive -Command '$ErrorActionPreference="Stop"; try { $status=tailscale status --json; if ($LASTEXITCODE -ne 0) { exit 1 }; ($status | ConvertFrom-Json).Self.DNSName.TrimEnd(".") } catch { exit 1 }' | tr -d '\r')"
  if [[ ! "$TS_HOST" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)+\.ts\.net$ ]]; then
    echo "!! Windows Tailscale did not return a valid tailnet DNS name; pairing was not generated." >&2
    exit 1
  fi
  BASE_URL="https://$TS_HOST/ceviz"
  PAIRING_METHOD=tailscale
elif [ "$NETWORK_MODE" = relay ] && [ "$IS_WSL" = 1 ]; then
  BASE_URL="$(install_windows_relay)"; PAIRING_METHOD=relay
  echo "==> Windows LAN relay: $BASE_URL"
else
  echo "==> Manuel ag modu — erisilebilir backend adresini uygulamaya gir"
fi

# --- 6) Pairing QR + bilgi ---
echo ""
echo "======================================================================"
echo "  Kurulum tamam. Telefonda Ceviz > Ayarlar > QR Tara ile oku:"
echo "======================================================================"
"$PY" - "$BASE_URL" "$TOKEN" "$PAIRING_METHOD" <<'PYEOF'
import sys, urllib.parse
base, token, method = sys.argv[1], sys.argv[2], sys.argv[3]
uri = "ceviz://pair?u=" + urllib.parse.quote(base, safe="") + "&t=" + urllib.parse.quote(token, safe="") + "&m=" + urllib.parse.quote(method, safe="")
try:
    import qrcode
    qr = qrcode.QRCode(border=1)
    qr.add_data(uri); qr.make(fit=True)
    qr.print_ascii(invert=True)
except Exception as e:
    print("(QR ciziminde sorun:", e, "— asagidaki bilgiyi elle gir)")
print()
print("  Sunucu adresi :", base)
print("  Token         :", token)
print("  Pairing URI   :", uri)
PYEOF
echo "======================================================================"
echo "  Tanilama icin: bash deploy/doctor.sh"

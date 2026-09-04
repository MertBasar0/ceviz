#!/usr/bin/env bash
# Ceviz Doctor — read-only installation and connectivity checks.
# The report never prints pairing tokens, APNs tokens, or command contents.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${WATCH_CEVIZ_PORT:-8080}"
VENV_PY="$APP_DIR/.venv/bin/python"
TOKEN_FILE="$APP_DIR/.auth-token"
FAILURES=0
WARNINGS=0

pass() { printf 'PASS  %s\n' "$1"; }
warn() { printf 'WARN  %s\n' "$1"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf 'FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

printf 'Ceviz Doctor\n'
printf '============\n'
printf 'Platform: %s\n' "$(uname -srm 2>/dev/null || printf unknown)"
printf 'Install:  %s\n\n' "$APP_DIR"

if command -v openclaw >/dev/null 2>&1; then
  pass "OpenClaw CLI is available on PATH"
else
  fail "OpenClaw CLI is not available on PATH"
fi

if command -v python3 >/dev/null 2>&1; then
  pass "Python 3 is available"
else
  fail "Python 3 is not available"
fi

if [ -x "$VENV_PY" ]; then
  pass "Ceviz virtual environment exists"
  if "$VENV_PY" -c 'import faster_whisper, qrcode' >/dev/null 2>&1; then
    pass "Local Whisper and QR dependencies import successfully"
  else
    fail "Backend dependencies are incomplete; rerun deploy/install.sh"
  fi
else
  fail "Ceviz virtual environment is missing; run deploy/install.sh"
fi

TOKEN=""
if [ -f "$TOKEN_FILE" ]; then
  TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
  if [ -n "$TOKEN" ]; then
    pass "Pairing token exists (value hidden)"
  else
    fail "Pairing token file is empty"
  fi

  TOKEN_MODE=""
  if stat -c '%a' "$TOKEN_FILE" >/dev/null 2>&1; then
    TOKEN_MODE="$(stat -c '%a' "$TOKEN_FILE")"
  elif stat -f '%Lp' "$TOKEN_FILE" >/dev/null 2>&1; then
    TOKEN_MODE="$(stat -f '%Lp' "$TOKEN_FILE")"
  fi
  case "$TOKEN_MODE" in
    600|400) pass "Pairing token permissions are private ($TOKEN_MODE)" ;;
    "") warn "Could not verify pairing token permissions" ;;
    *) warn "Pairing token permissions are $TOKEN_MODE; use chmod 600 .auth-token" ;;
  esac
else
  fail "Pairing token is missing; run deploy/install.sh"
fi

if command -v git >/dev/null 2>&1 && git -C "$APP_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "$APP_DIR" ls-files --error-unmatch .auth-token >/dev/null 2>&1; then
    fail "Pairing token is tracked by Git; remove it from version control"
  else
    pass "Pairing token is not tracked by Git"
  fi
fi

SERVICE_ACTIVE=0
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  if systemctl --user is-active --quiet watch-ceviz-backend; then
    SERVICE_ACTIVE=1
    pass "watch-ceviz-backend user service is active"
  else
    fail "watch-ceviz-backend user service is not active"
  fi
elif command -v pgrep >/dev/null 2>&1 && pgrep -f "backend/main.py $PORT" >/dev/null 2>&1; then
  SERVICE_ACTIVE=1
  pass "Ceviz backend process is running (non-systemd mode)"
else
  fail "Ceviz backend process was not found"
fi

if [ "$SERVICE_ACTIVE" -eq 1 ] && [ -x "$VENV_PY" ] && [ -n "$TOKEN" ]; then
  if printf '%s' "$TOKEN" | CEVIZ_DOCTOR_PORT="$PORT" "$VENV_PY" -c '
import os, sys, urllib.request
token = sys.stdin.read()
url = "http://127.0.0.1:%s/api/v1/jobs/active" % os.environ["CEVIZ_DOCTOR_PORT"]
req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
with urllib.request.urlopen(req, timeout=5) as response:
    if response.status != 200:
        raise SystemExit(1)
' >/dev/null 2>&1; then
    pass "Authenticated local backend request succeeded"
  else
    fail "Authenticated local backend request failed on port $PORT"
  fi
else
  warn "Local authenticated request skipped until service, environment, and token checks pass"
fi

if command -v tailscale >/dev/null 2>&1; then
  if tailscale status >/dev/null 2>&1; then
    pass "Tailscale is connected"
  else
    warn "Tailscale is installed but not connected"
  fi
elif grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe >/dev/null 2>&1; then
  if powershell.exe -NoProfile -Command 'tailscale status *> $null; exit $LASTEXITCODE' >/dev/null 2>&1; then
    pass "Tailscale is connected on the Windows host"
  else
    warn "Tailscale was not detected in WSL or on the Windows host"
  fi
else
  warn "Tailscale was not detected; this is expected for manual or same-Wi-Fi setups"
fi

printf '\nSummary: %d failure(s), %d warning(s).\n' "$FAILURES" "$WARNINGS"
printf 'No credentials or command contents were printed.\n'

if [ "$FAILURES" -gt 0 ]; then
  exit 1
fi

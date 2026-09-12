# Ceviz — Installation and safe updates

A fresh installation and an update to a working installation are different
operations. Run these commands on the OpenClaw machine as the user who runs
Ceviz. Do not run the updater with `sudo`.

This guide targets **ceviz-helper-v2026.9.12-beta.1**, matching the existing
TestFlight app **2026.6.5 (1789005793)**. See the
[helper release notes](../docs/release-notes-helper-2026.9.12-beta.1.md) for
validation coverage and limitations.

## Fresh installation

You need Python **3.11+**, `venv`, Git and OpenClaw. If Ceviz is already
installed, skip this section and use the existing-installation update guide.

Use an ordinary Linux home-directory path, such as `$HOME/ceviz`, without
spaces, percent signs or other special characters. The fresh installer's
generated service paths do not yet support arbitrary directory names. This is
separate from spaces in the shell's `PATH`, which the installer quotes when
passing it to the service.

```bash
git clone --branch ceviz-helper-v2026.9.12-beta.1 --single-branch https://github.com/MertBasar0/ceviz.git
cd ceviz
bash deploy/install.sh
```

The installer creates a Python environment and installs dependencies, including
CUDA libraries when it detects a GPU. It generates a pairing token, creates a
service, configures the selected connection method and displays a pairing QR.
Linux/WSL uses a systemd user service when available. The installer's `nohup`
fallback, macOS and other non-systemd installations are outside the automatic
updater's supported scope.

On iPhone, open **Ceviz → Settings → Scan pairing QR → Test connection → Save**.
The QR contains the backend address and bearer token; do not share it. Updating
an existing installation does not require pairing again.

<a id="mevcut-kurulumu-guncelle"></a>
<a id="update-existing-installation"></a>

## Update an existing installation

Automatic updating supports only Linux/WSL installations using the same user's
persistent `watch-ceviz-backend.service` **systemd user service**. macOS,
`nohup`, custom launch commands, local backend modifications or different
Python dependencies require assisted updating. Re-running the installer is not
a safe alternative.

First set the actual installation directory; `/absolute/path/to/ceviz` below
is a placeholder. Download the new updater into a separate temporary directory
and run its read-only check:

```bash
CEVIZ_INSTALL_DIR="/absolute/path/to/ceviz"
CEVIZ_UPDATE_DIR="$(mktemp -d)"
curl --fail --location --proto '=https' --tlsv1.2 \
  'https://raw.githubusercontent.com/MertBasar0/ceviz/ceviz-helper-v2026.9.12-beta.1/deploy/update.py' \
  --output "$CEVIZ_UPDATE_DIR/update.py" &&
python3 "$CEVIZ_UPDATE_DIR/update.py" --install-dir "$CEVIZ_INSTALL_DIR" --check
```

`--check` does not stop the service, download a source release or change files
and settings. Do not continue if a job is running or conversation delivery is
unconfirmed. Review the result in Ceviz and contact support if it remains
unresolved; never delete tracking records to bypass this check. `READY` means
the installation was idle when checked, not that every later update check has
passed or that new requests have been prevented.

After a successful check, **close Ceviz on both iPhone and Watch** and stop
requests from Shortcuts or any other Ceviz client. Keep this maintenance window
until the updater reports `UPDATED`, `UP TO DATE`, or successful `RECOVERED`.
In the same terminal, explicitly confirm that no requests will be sent:

```bash
read -r -p 'All Ceviz clients are closed and no commands will be sent until maintenance finishes. Type UPDATE to confirm: ' CEVIZ_CONFIRM
if [ "$CEVIZ_CONFIRM" = "UPDATE" ]; then
  python3 "$CEVIZ_UPDATE_DIR/update.py" \
    --install-dir "$CEVIZ_INSTALL_DIR" \
    --revision ceviz-helper-v2026.9.12-beta.1 \
    --yes-maintenance
fi
```

The updater resolves the full Git commit identity and verifies a complete
snapshot of the backend and contracts. It replaces only `backend/main.py` with
a launcher for that snapshot, rather than overwriting runtime modules one at a
time. Only the Ceviz service is briefly stopped and started. Authentication,
capabilities, the session list and, when a suitable session exists, history are
checked read-only; no real command is sent.

Pairing, existing service/environment settings, the Python environment,
Tailscale/relay/network settings, job history and conversation delivery records
are preserved. OpenClaw's Gateway, model and permissions are not changed. If a
release changes Python dependencies, automatic updating stops without installing
packages and asks for assisted updating.

Use this tool for later updates too. Do not use `git pull`, `git reset`, old
file copies or `install.sh` to update a managed installation. Keep
`.ceviz-updates`: it contains running source snapshots, code backups and update
receipts. These are not backups of conversation text or tokens, but they contain
local paths and job identifiers; do not publish them as support logs.

The original checkout's deployment scripts and Git revision stay unchanged;
the running helper version is recorded by the updater, not by `git log` in
that checkout. Download the updater from the published guide for each release.
An older checkout's Doctor may lack the new capability check or suggest an
installer rerun: do not follow that suggestion. Use the downloaded updater's
`--check` and its verified update result for the current maintenance flow.

### Recover an interrupted update

If activation fails, the updater attempts to restore the previous code. If the
process was interrupted or reports `RECOVERY REQUIRED`, keep all clients idle.
Use the same downloaded updater and the same installation:

```bash
python3 "$CEVIZ_UPDATE_DIR/update.py" \
  --install-dir "$CEVIZ_INSTALL_DIR" --recover --yes-maintenance
```

`--recover` restores only the verified previous code of a pending update. It
does not rewind job/conversation state, delete delivery guards or resend
commands. Recovery may refuse if settings or state changed; contact support
before sending new commands. Without a pending update, this is not a general
downgrade command.

If the temporary directory or terminal is gone, download the same published
updater again from the HTTPS URL above and set the real installation directory
again. Leave the records in `.ceviz-updates` intact. The previous code restored
by recovery may not include the newer Conversations features.

### Trusted local source for maintainers

For a reviewed offline/staged update, a maintainer can add
`--source /path/to/trusted/ceviz` and set `--revision` to an exact 40-character
commit or published helper release tag. The selected Git commit is used, not
uncommitted files in that checkout. This does not bypass maintenance approval,
idle checks or settings/state protection. Normal users should omit `--source`;
the updater fetches only the official Ceviz GitHub repository into a temporary
directory.

## Ceviz Doctor

After installation, or when pairing or delivery fails, run this from the
installation directory:

```bash
bash deploy/doctor.sh
```

Doctor checks OpenClaw and Python availability, virtual-environment
dependencies, token existence/permissions, service status, authenticated local
access, helper capabilities and Tailscale. It is read-only and does not print
token values, APNs tokens or command contents. Follow its repair guidance;
do not reinstall over a working installation.

### Connection mode for a fresh installation

- `WATCH_CEVIZ_NETWORK_MODE=tailscale`: recommended private tailnet access
  across different networks.
- `WATCH_CEVIZ_NETWORK_MODE=relay`: WSL2 + Windows same-LAN relay; requires
  Windows UAC approval.
- `WATCH_CEVIZ_NETWORK_MODE=manual`: your existing VPN/tunnel/reverse-proxy URL.
- `auto` (default): asks in an interactive terminal; detects an available
  method during non-interactive installation.

## Optional fresh-installation environment variables

| Variable | Default | Purpose |
|---|---|---|
| `WATCH_CEVIZ_PORT` | `8080` | Backend port |
| `WATCH_CEVIZ_NETWORK_MODE` | `auto` | `tailscale`, `relay`, `manual`, or automatic selection |
| `WATCH_CEVIZ_WHISPER_MODEL` | `large-v3` with GPU, otherwise `small` | Speech-to-text model |
| `WATCH_CEVIZ_WHISPER_LANGUAGE` | `tr` | Default speech-to-text language |
| `OPENCLAW_WATCH_AGENT` | `main` | OpenClaw agent used for Watch commands |

The updater does not reselect these values or write them into your existing
service.

## WSL2 + Windows connection note

The Windows lifecycle repair below is a **repair candidate**, not yet included
in the `ceviz-helper-v2026.9.12-beta.1` download above. Use a reviewed repair
source folder supplied for your installation; do not assume the old tag has
these scripts or rerun its installer to repair an existing setup.

When Tailscale runs on Windows, the repaired fresh installer verifies the
authenticated Ceviz backend at Windows `127.0.0.1:<port>` before publishing
that address. It does not create a LAN listener or firewall rule for Tailscale.
For an assisted/manual setup with a Windows-reachable backend on port 8080,
the corresponding Windows-side command is:

```powershell
tailscale serve --bg --set-path=/ceviz http://127.0.0.1:8080
```

Only use that address after verifying Windows can reach the backend there.
If localhost forwarding is unavailable in a custom WSL configuration, stop and
request assistance; do not silently substitute a LAN address or open the
firewall. The separate LAN relay remains an explicit `relay` connection mode.
Its legacy recovery is limited: a LAN address change does not update its firewall
binding, and extended loss of a default route can exhaust its three retries.
Those conditions need operator assistance; the independent lifetime task and
Windows Tailscale localhost route do not rely on that relay.
Pair iPhone with
`https://<machine-name>.<tailnet>.ts.net/ceviz` and its private token. These are
initial networking instructions, not part of the code-only update.

### Windows lifetime repair for an existing WSL installation

An enabled systemd service does **not** keep WSL alive. The repaired setup uses
an independent **Ceviz WSL Lifetime** Windows scheduled task. It holds one
foreground WSL client for the selected distribution, starts at Windows logon,
and checks once per minute whether another instance can start. Its action runs
`System32\wsl.exe --distribution "YOUR_DISTRO" --exec /bin/sleep infinity`
directly, so the tracked process is the foreground client, not a PowerShell
wrapper with a separately owned child. `IgnoreNew`
prevents overlapping task instances; there is no task execution time limit or
network/idle/battery prerequisite. The Windows user must be logged in and the
computer awake. Windows sleep, logoff or a disconnected VPN still interrupts
access; task state alone is not backend health or command-delivery proof.

First inspect from **Windows PowerShell**, before opening a Linux terminal:

```powershell
wsl.exe --list --verbose
Get-ScheduledTask -TaskName 'Ceviz WSL Lifetime' -ErrorAction SilentlyContinue
Get-ScheduledTaskInfo -TaskName 'Ceviz WSL Lifetime' -ErrorAction SilentlyContinue
```

These checks do not start a stopped distro. Running a command *inside* WSL,
including Linux Doctor, can start it and its enabled services; that temporary
availability is not evidence that the outage was repaired.

After an explicit maintenance approval, close Ceviz clients and use the
reviewed repair source folder in Windows PowerShell. Replace `YOUR_DISTRO`
with the exact registered name shown above:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\deploy\windows\install-wsl-lifetime.ps1 -Distro 'YOUR_DISTRO'
```

This registers and starts only the independent lifetime task. It does not
rewrite the Ceviz service, pairing token, jobs, conversation records, Python
environment, Gateway settings or Tailscale target. Starting WSL can naturally
start its already-enabled Linux services. The old LAN relay is not required
for Tailscale and is not restarted by this command. Its retirement, if needed,
is a separate reviewed Windows maintenance action.

An existing task is replaced only when its exact component, Windows user and
distro match; its previous XML definition remains available under
`%LOCALAPPDATA%\Ceviz\wsl-lifetime`. No custom lifetime runtime is copied.
Unknown, modified, running or disabled-for-maintenance tasks require operator
review before replacement. A registration/start/readback error is a failure,
not a successful repair: retain the backups and inspect Task Scheduler before
continuing. The code-only helper updater deliberately does not install or
update Windows tasks and does not overwrite deployment scripts in old checkouts.

For an intentional WSL shutdown or lifetime-task upgrade, first pause clients
and disable the lifetime task, then stop that exact task; otherwise its
one-minute trigger will bring WSL back. Do not kill arbitrary WSL processes.
Re-enable/start the reviewed task when maintenance ends. Confirm from Windows
that it stays Running, that the selected distro remains running after all
Linux terminals close, and that Ceviz's existing authenticated connection still
works. Do not re-pair, clear pending requests or resend an unconfirmed command
to test host availability.

Real-host validation must also check the task's stop/restart behavior and
whether the interactive Windows session shows a console window; isolated tests
do not prove these Task Scheduler/WSL behaviors. A window-free launch is not
claimed until that approved maintenance check passes.

If a fresh installation stops during its network or task step, a service/token
may already have been created. Do not rerun `install.sh`, delete that token or
re-pair as recovery: the existing-install guard intentionally stops another
fresh installation. Keep the output and request assisted repair of the failed
boundary. The older native-Linux Tailscale branch still needs separate
serve/DNS failure handling. Doctor's `.auth-token` check also does not cover
legacy service-environment-only token storage; a missing token-file warning
alone is not proof that such a recovered installation lost its token.

Microsoft documents the relevant boundaries: [systemd and WSL lifetime](https://learn.microsoft.com/en-us/windows/wsl/systemd),
[Windows localhost access to WSL](https://learn.microsoft.com/en-us/windows/wsl/networking), and
[Task Scheduler settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).

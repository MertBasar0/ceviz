# Ceviz

[![Ceviz Watch App Build](https://github.com/MertBasar0/ceviz/actions/workflows/ceviz-watch-build.yml/badge.svg)](https://github.com/MertBasar0/ceviz/actions/workflows/ceviz-watch-build.yml)

Ceviz is an Apple Watch and iPhone control surface for OpenClaw. Speak a short
command on your watch, run the job through the OpenClaw installation on your own
machine, read the summary on your wrist, and open the full report on iPhone.

## Open beta

- [Join on TestFlight](https://testflight.apple.com/join/nEdn2Np2)
- [Product overview](https://basarlabs.com.tr/ceviz/)
- [Privacy policy](https://basarlabs.com.tr/ceviz/privacy/)

You need an iPhone, an Apple Watch, and OpenClaw running on a machine you
control. Ceviz operates no hosted command backend; the app connects to the
backend you install on your own machine over your private network.

## Requirements

- iPhone with iOS 16 or later
- Apple Watch with watchOS 9 or later
- OpenClaw installed and available on the backend machine's `PATH`
- Python 3 with `venv` support
- Tailscale, a private VPN, or local-network access to the backend machine

WSL2 is currently the most thoroughly validated installation path. macOS and
bare Linux are supported beta targets and still need broader real-world
feedback.

## Install the backend

Run these commands on the machine where OpenClaw is installed:

```bash
git clone https://github.com/MertBasar0/ceviz.git
cd ceviz
bash deploy/install.sh
```

The installer:

1. creates a Python virtual environment and installs the backend dependencies;
2. generates a local bearer token;
3. installs and starts a user service where supported;
4. configures the selected network path; and
5. prints a pairing QR code.

The first voice command may take a few minutes while the local Whisper model is
downloaded. Later commands reuse the downloaded model.

## Choose a connection

The installer asks which connection mode to use:

- **Tailscale — recommended:** private access when the phone and backend are on
  different networks. Enable VPN On Demand on iPhone so background access can
  recover reliably.
- **Windows relay:** intended for WSL2 when the Windows host, iPhone, and Watch
  are reachable on the same local network.
- **Manual:** use your own private VPN, HTTPS reverse proxy, or secure tunnel.

Do not expose the backend directly to the public internet over plain HTTP.
Ceviz accepts plain HTTP only for documented local-network relay addresses.

See [deploy/README.md](deploy/README.md) for network options and
[STT-SETUP.md](STT-SETUP.md) for local speech-to-text configuration.

## Pair the iPhone app

1. Install Ceviz from TestFlight and open it on the paired iPhone.
2. Open **Settings** from the gear icon.
3. Choose **Scan pairing QR** and scan the QR printed by the installer.
4. Test the connection, then save it.
5. Open Ceviz on Apple Watch and send a short, focused command.

The QR code contains the backend address and bearer token. Treat the QR image
and `.auth-token` file as credentials: do not publish, commit, or send them in
an issue.

Without a configured backend, the app opens in Demo Mode with sample data so
the interface can be explored without an account or server.

## Repository layout

- `apple-watch/` — watchOS app
- `ios-bridge/` — iPhone companion app
- `backend/` — self-hosted Python backend and OpenClaw adapter
- `deploy/` — installer, service, and Windows/WSL2 relay
- `contracts/` — request and response schemas
- `tests/` — backend, contract, push, and structured-output tests
- `fastlane/` — signed build and TestFlight automation
- `docs/` — App Store, privacy, release, and launch material

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Security

Report suspected vulnerabilities privately as described in
[SECURITY.md](SECURITY.md). Never place pairing tokens, signing credentials,
voice content, or unredacted job reports in a public issue.

## License and trademarks

Except for the reserved assets governed by
[BRAND-ASSET-LICENSE](BRAND-ASSET-LICENSE) and identified in
[TRADEMARKS.md](TRADEMARKS.md), the source code and documentation are licensed
under the [Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE) for
attribution.

`Ceviz`, the Ceviz logo, application icons, and associated product identity are
claimed as trademarks of Mert Başar. All trademark rights are reserved. The
Apache License does not grant permission to use Ceviz branding for a fork or
commercial distribution.

# Ceviz

Ceviz is an Apple Watch and iPhone control surface for OpenClaw. Speak a short
command on your watch, run the job through the OpenClaw installation on your own
machine, read the summary on your wrist, and open the full report on iPhone.

## Open beta

- [Join on TestFlight](https://testflight.apple.com/join/nEdn2Np2)
- [Product and setup overview](https://basarlabs.com.tr/ceviz/)
- [Privacy policy](https://basarlabs.com.tr/ceviz/privacy/)

You need an iPhone, an Apple Watch, and an OpenClaw installation on a machine
you control. Ceviz operates no hosted backend; the app connects to the backend
you install on your own machine over your private network.

## Repository layout

- `apple-watch/` — watchOS app
- `ios-bridge/` — iPhone companion app
- `backend/` — self-hosted Python backend and OpenClaw adapter
- `deploy/` — installer, service, and Windows/WSL2 relay
- `contracts/` — request and response schemas
- `tests/` — backend, contract, push, and structured-output tests
- `fastlane/` — signed build and TestFlight automation
- `docs/` — App Store, privacy, release, and launch material

## Local backend setup

From a clone of this repository:

```bash
bash deploy/install.sh
```

The installer starts the backend and prints a pairing QR code. Scan it from the
Ceviz iPhone app. Tailscale is the recommended connection for private access
across different networks.

See [deploy/README.md](deploy/README.md) for supported setup options and
[STT-SETUP.md](STT-SETUP.md) for local speech-to-text configuration.

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

WSL2 is currently the most thoroughly validated installation path. Independent
onboarding, macOS, and bare-Linux installations remain open-beta feedback
targets.

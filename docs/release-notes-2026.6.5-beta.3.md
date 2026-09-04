# Ceviz 2026.6.5 Beta 3

Beta 3 makes Ceviz easier to trust, diagnose, and use outside Turkish-language
setups while sharpening its role as the local-first, Watch-first voice task
layer for OpenClaw.

## Fixed

- English devices no longer receive reports that are accidentally forced into
  Turkish by the backend prompt.
- Processing, failure, handoff, missing-job, and completion-notification
  fallbacks now follow the originating device locale.
- Microphone and camera permission descriptions default to English and retain
  explicit Turkish localizations.
- English and Turkish string catalogs are checked for matching keys in the
  automated test suite.

## Added

- `bash deploy/doctor.sh` runs read-only checks for OpenClaw, Python, the Ceviz
  environment, local Whisper, pairing-token permissions, backend service,
  authenticated local access, and Tailscale. Its report does not print tokens
  or command contents.
- A public security and data-flow model explains why the local backend exists,
  what it can access, how completion notifications work, and how to remove a
  Ceviz installation.
- The product strategy now explicitly positions Ceviz as a focused Watch-first
  layer rather than a replacement for the full OpenClaw mobile client.

## Privacy clarification

- Voice audio, full transcripts, full reports, and the backend token are not
  sent to the hosted notification relay.
- To deliver background notifications, the relay stores the APNs device token,
  bundle identifier, random installation identifier, and a hash of its send
  grant for up to 180 days. Notification titles, concise summaries, and routing
  identifiers pass through the relay to APNs and are not end-to-end encrypted
  by Ceviz.
- The privacy policy and published App Store privacy answers now describe this
  path accurately.

## Validation

- **40/40** backend, contract, push, and localization tests pass locally.
- Installer and Doctor scripts pass Bash syntax validation.
- Signed iOS/watchOS archive and TestFlight upload passed in GitHub Actions.
- Build `1788552567` was accepted as `VALID`, assigned to the public external
  `Beta` group, and verified as `IN_BETA_TESTING` for both internal and external
  testing.

## Links

- [Join the open beta on TestFlight](https://testflight.apple.com/join/nEdn2Np2)
- [Product and setup overview](https://basarlabs.com.tr/ceviz/)
- [Security and data-flow model](security-model.md)
- [Privacy policy](https://basarlabs.com.tr/ceviz/privacy/)

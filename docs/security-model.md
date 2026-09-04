# Ceviz security and data-flow model

Last updated: **4 September 2026**

## Why there is a local backend

Apple Watch and iPhone do not run the user's OpenClaw installation or the local
Whisper model. The Ceviz backend is the narrow adapter between those devices and
the OpenClaw CLI on the user's own machine. It accepts an authenticated voice
command, transcribes it, starts an OpenClaw job, stores recent job state, and
returns a Watch-sized summary plus an optional iPhone report.

The backend is not hosted by Basar Labs. Each user installs and controls their
own instance.

## Normal command path

1. Apple Watch records audio only after the user starts recording.
2. The audio moves to the paired iPhone through Apple's WatchConnectivity.
3. iPhone sends it to the backend URL selected by the user, with the bearer
   token generated during installation.
4. The backend transcribes audio with local Whisper by default. It sends audio
   to an external speech service only when the user explicitly configures one.
5. The backend invokes the local OpenClaw CLI and keeps the recent job state on
   that machine.
6. The result returns to iPhone and Apple Watch. The Watch receives the concise
   outcome; the complete report remains available on iPhone.

The pairing bearer token is stored in iOS Keychain and in the user's backend
installation. Pairing QR codes contain that token and must be treated as
credentials.

## Completion notification relay

Ceviz uses a small hosted relay to deliver background notifications through
Apple Push Notification service (APNs). This relay is separate from the command
backend and cannot run OpenClaw commands.

Registration sends the APNs device token, bundle identifier, and a random
installation identifier to the relay. The relay stores that registration and a
hash of its send grant for up to 180 days. A completion notification passes the
notification title, concise Watch summary, job identifier, job status, deep
link, and handoff flag through the relay to APNs. It does **not** include voice
audio, the full transcript, the full phone report, or the backend pairing
token. The notification summary can still contain sensitive information, so it
should not be treated as end-to-end encrypted content.

The relay source is in [`push-worker/`](../push-worker/). Advanced users can
point the backend to a compatible self-hosted relay with
`WATCH_CEVIZ_PUSH_RELAY_URL`.

## Access boundaries

- The backend bearer token authorizes Ceviz API requests. Anyone who obtains it
  and can reach the backend should be treated as having the ability to start
  OpenClaw jobs.
- Tailscale or another private VPN is the recommended network boundary. The
  backend must not be exposed directly to the public internet over plain HTTP.
- The OpenClaw process runs with the permissions of the account that installed
  the Ceviz service. Ceviz does not add an independent OpenClaw permission
  sandbox.
- The repository contains no production pairing token, APNs private key, Apple
  signing certificate, or App Store Connect key.

## Diagnostics and support

Run `bash deploy/doctor.sh` for a read-only report. It checks installation,
service, authentication, local dependencies, and network prerequisites without
printing credentials or command contents. Redact hostnames or filesystem paths
as desired before posting the report publicly.

## Removing a local installation

From the machine where Ceviz was installed:

1. Stop and disable `watch-ceviz-backend` with the user service manager, if it
   was installed as a systemd user service.
2. Remove the generated user service file and reload the user service manager.
3. Remove the Ceviz repository directory, including `.auth-token`, `.venv`, and
   local backend logs.
4. Remove `~/.openclaw/ceviz-state` if the recent Ceviz job history and push
   registration should also be erased.
5. Review `tailscale serve status` and remove the `/ceviz` route if the installer
   created one. Do not reset unrelated Tailscale Serve routes.
6. Delete the Ceviz iPhone/Watch application to remove its local settings and
   Keychain credential.

If a pairing QR or token may have been exposed, regenerate the backend token
and pair the application again.

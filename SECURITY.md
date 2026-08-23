# Security policy

## Supported versions

Ceviz is currently in open beta. Security fixes are applied to the latest
TestFlight build and the current `main` branch. Older builds should be treated
as unsupported once a replacement is available.

## Reporting a vulnerability

Do not open a public GitHub issue for a suspected vulnerability.

Email `mert@basarlabs.com.tr` with the subject `Ceviz security report` and
include, where possible:

- the affected component and version or commit;
- a concise description of the impact;
- reproducible steps or a minimal proof of concept;
- relevant logs with access tokens, voice content, personal data, and machine
  identifiers removed; and
- whether you believe the issue is being actively exploited.

Please do not access data that is not yours, degrade third-party systems, or
publish exploit details before a fix and disclosure timeline are coordinated.

The response targets are acknowledgment within three business days and a
status update within seven business days. These are targets rather than a
service-level guarantee. There is currently no paid bug-bounty program.

## In scope

Examples include:

- authentication bypass or exposure of the backend bearer token;
- unauthorized command execution against OpenClaw;
- insecure transport accepted outside the documented local-network exception;
- push registration or notification spoofing;
- leakage of voice recordings, transcripts, job reports, or Keychain values;
- vulnerabilities in QR pairing or backend endpoint validation; and
- supply-chain issues in the installer, build workflow, or distributed app.

## Operational precautions

- Treat pairing QR codes and `.auth-token` as credentials.
- Use Tailscale or another private network for access across networks.
- Do not expose the backend directly to the public internet over plain HTTP.
- Revoke and replace credentials immediately if they may have been disclosed.
- Never attach signing keys, App Store Connect keys, `.p12` files, bearer
  tokens, or unredacted user content to an issue.

Vulnerabilities in OpenClaw itself should also be reported through OpenClaw's
own security channel.

# Ceviz product strategy

Last updated: **4 September 2026**

## Positioning

**Ceviz is the local-first, Watch-first voice command and task-completion layer
for OpenClaw.**

Ceviz is not intended to replace the official OpenClaw iPhone application. The
official application is the broad mobile client for chat, sessions, approvals,
automations, skills, files, and device capabilities. Ceviz deliberately focuses
on one narrower workflow:

> Speak a short request on Apple Watch, run it on the OpenClaw installation you
> control, receive a glanceable result on your wrist, and continue with the full
> report on iPhone only when needed.

## Product principles

1. **The Watch is the primary surface.** The common path must remain fast,
   glanceable, and usable without opening the iPhone application.
2. **Local-first is a product feature.** Speech is transcribed locally by
   default, jobs run beside the user's own OpenClaw installation, and Ceviz does
   not operate a hosted command backend.
3. **Asynchronous work must feel dependable.** A command may outlive a screen,
   network transition, or application process. Its state and terminal result
   must remain visible and consistent.
4. **Depth moves to the phone.** The Watch shows the outcome and the next useful
   action; long reports, corrections, and multi-step choices belong on iPhone.
5. **Setup must explain and diagnose itself.** A self-hosted component is an
   acceptable trade-off only when installation, security boundaries, and
   recovery are understandable.
6. **Specialise instead of matching feature lists.** Features are added when
   they improve the Watch-first workflow, not to recreate the full OpenClaw
   mobile client.

## Near-term release gates

### Beta 3 — confidence and onboarding

- Remove Turkish leakage from the English application and generated fallback
  states.
- Add a Ceviz Doctor command that checks OpenClaw, speech-to-text, service,
  authentication, network reachability, and pairing prerequisites without
  exposing secrets.
- Explain why the local backend exists, what it can access, where data flows,
  and how to remove it.
- Turn the first external tester's feedback into a short, reproducible
  acceptance checklist.

### Beta 4 candidate — fastest path from the wrist

- Add a Watch-face complication/widget that opens directly into voice capture.
- Measure cold-start, record-to-acknowledgement, and result-notification time.
- Validate the flow on more than one Watch size and at least one independent
  installation.

## Growth loop

1. Publish a focused promise rather than a generic mobile-client claim.
2. Send new testers to one install page and one TestFlight link.
3. Ask for feedback at four observable points: install, pair, first command,
   and first completed result.
4. Convert repeated friction into Doctor checks, documentation, or product
   changes.
5. Publish small releases with an explicit user-visible improvement and invite
   the affected tester to verify it.

## Measures that matter during open beta

- Successful first pairing
- Successful first real voice command
- Completed result seen on Watch without opening Ceviz on iPhone
- Time from install start to first completed result
- Seven-day repeat use
- Failure reason and recovery path when any stage does not complete

Raw download or TestFlight join counts are useful context, but they do not
replace these activation and reliability measures.

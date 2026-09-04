import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";
import worker from "../../push-worker/src/index.js";

const keyPair = await webcrypto.subtle.generateKey(
  { name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"],
);
const privateKey = Buffer.from(await webcrypto.subtle.exportKey("pkcs8", keyPair.privateKey)).toString("base64");

function environment() {
  const records = new Map();
  return {
    APNS_KEY_ID: "SYNTHETIC",
    APNS_TEAM_ID: "TESTTEAM",
    APNS_PRIVATE_KEY: `-----BEGIN PRIVATE KEY-----\n${privateKey}\n-----END PRIVATE KEY-----`,
    REGISTRATIONS: {
      async put(key, value) { records.set(key, value); },
      async get(key) { return records.get(key) ?? null; },
      async delete(key) { records.delete(key); },
    },
  };
}

function request(path, body, grant) {
  return new Request(`https://relay.example.test${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(grant ? { authorization: `Bearer ${grant}` } : {}) },
    body: JSON.stringify(body),
  });
}

async function register(env) {
  const response = await worker.fetch(request("/v1/register", {
    apnsToken: "a".repeat(64), bundleId: "test.ceviz.watch", installationId: "test-installation",
  }), env);
  assert.equal(response.status, 200);
  const registration = await response.json();
  assert.equal(registration.ok, true);
  return registration;
}

test("registered sends preserve each allowed outcome and only the existing notification fields", async (t) => {
  const env = environment();
  const registration = await register(env);
  const delivered = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, `https://api.push.apple.com/3/device/${"a".repeat(64)}`);
    assert.equal(options.headers["apns-topic"], "test.ceviz.watch");
    assert.match(options.headers.authorization, /^bearer [\w-]+\.[\w-]+\.[\w-]+$/);
    delivered.push(JSON.parse(options.body));
    return new Response("", { status: 200, headers: { "apns-id": "synthetic-id" } });
  });
  for (const outcome of ["done", "blocked", "needs_input", "unknown"]) {
    const response = await worker.fetch(request("/v1/send", {
      relayHandle: registration.relayHandle, jobId: "job-test", status: "completed", outcome,
      title: "Ceviz result", message: "A short report", watchSummary: "A short report",
      deepLink: "ceviz://job/job-test", requiresPhoneHandoff: true,
      transcript: "Must not leave the user's backend", phoneReport: "Private long report",
    }, registration.sendGrant), env);
    assert.equal(response.status, 200);
    assert.equal((await response.json()).ok, true);
    const payload = delivered.at(-1);
    assert.deepEqual(Object.keys(payload).sort(), [
      "aps", "deep_link", "job_id", "job_status", "outcome", "requires_phone_handoff", "watch_summary",
    ]);
    assert.equal(payload.outcome, outcome);
    assert.equal(payload.job_status, "completed");
    assert.equal(payload.watch_summary, "A short report");
    assert.equal(payload.requires_phone_handoff, true);
  }
  assert.equal(delivered.length, 4);
});

test("missing or invalid outcome remains unknown and empty message is never success copy", async (t) => {
  const env = environment();
  const registration = await register(env);
  const delivered = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    delivered.push(JSON.parse(options.body));
    return new Response("", { status: 200 });
  });
  for (const outcome of [undefined, "verified_success", { secret: "do-not-forward" }]) {
    const response = await worker.fetch(request("/v1/send", {
      relayHandle: registration.relayHandle, status: "completed", outcome,
    }, registration.sendGrant), env);
    assert.equal(response.status, 200);
    assert.equal(delivered.at(-1).outcome, "unknown");
    assert.equal(delivered.at(-1).aps.alert.body, "Ceviz update.");
  }
});

test("missing and incorrect grants never reach APNs", async (t) => {
  const env = environment();
  const registration = await register(env);
  const apns = t.mock.method(globalThis, "fetch", async () => {
    assert.fail("Unauthenticated request reached APNs");
  });
  for (const grant of [undefined, "wrong-grant"]) {
    const response = await worker.fetch(request("/v1/send", {
      relayHandle: registration.relayHandle, outcome: "done",
    }, grant), env);
    assert.equal(response.status, 401);
  }
  assert.equal(apns.mock.callCount(), 0);
});

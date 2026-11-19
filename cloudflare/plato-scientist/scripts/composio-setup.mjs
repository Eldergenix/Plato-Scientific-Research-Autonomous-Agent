#!/usr/bin/env node
// Idempotent Composio setup for connected-service triggers:
//   1. find or create the webhook subscription that delivers trigger events to the Worker;
//   2. store its signing secret as the Worker secret COMPOSIO_WEBHOOK_SECRET (only when the
//      Worker does not have it yet; HAS_WEBHOOK_SECRET=1 skips it).
// Reads COMPOSIO_API_KEY from the environment. Never prints the key or the secret.
import { spawnSync } from "node:child_process";

const url = process.argv[2];
const key = process.env.COMPOSIO_API_KEY;
if (!url || !key) {
  console.error("usage: COMPOSIO_API_KEY=... node scripts/composio-setup.mjs <webhook url>");
  process.exit(2);
}
const BASE = "https://backend.composio.dev/api/v3";
const EVENTS = [
  "composio.trigger.message",
  "composio.connected_account.expired",
  "composio.trigger.disabled",
];

async function api(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { "x-api-key": key, ...(body ? { "content-type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path}: ${res.status} ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

const list = await api("GET", "/webhook_subscriptions");
const items = list.items ?? list.data ?? [];
let sub = items.find((s) => s.webhook_url === url);
let secret = null;
if (sub) {
  console.log(`Webhook subscription exists (${sub.id}).`);
  const enabled = new Set(sub.enabled_events ?? []);
  if (!EVENTS.every((e) => enabled.has(e))) {
    await api("PATCH", `/webhook_subscriptions/${sub.id}`, { enabled_events: EVENTS });
    console.log("Updated its events.");
  }
  if (process.env.HAS_WEBHOOK_SECRET !== "1") secret = (await api("GET", `/webhook_subscriptions/${sub.id}`)).secret ?? null;
} else {
  sub = await api("POST", "/webhook_subscriptions", { webhook_url: url, enabled_events: EVENTS, version: "V3" });
  secret = sub.secret ?? null;
  console.log(`Created webhook subscription ${sub.id}.`);
}
if (process.env.HAS_WEBHOOK_SECRET === "1" && !secret) {
  console.log("COMPOSIO_WEBHOOK_SECRET is already set on the Worker; keeping it.");
} else if (!secret) {
  console.error("Composio did not return the subscription secret; set COMPOSIO_WEBHOOK_SECRET by hand.");
  process.exit(1);
} else {
  const r = spawnSync("npx", ["wrangler", "secret", "put", "COMPOSIO_WEBHOOK_SECRET"], {
    input: secret,
    stdio: ["pipe", "inherit", "inherit"],
  });
  if (r.status !== 0) process.exit(r.status ?? 1);
  console.log("Stored COMPOSIO_WEBHOOK_SECRET on the Worker.");
}

// Smoke check: starts the app, runs every demo flow against it with real services, checks what
// comes back, and stops the app. Copy to scripts/smoke.mjs and add "smoke": "node scripts/smoke.mjs"
// to package.json (any stack: START can launch a Python server just as well).
// Exit 0: every flow works. Exit 1: a flow failed, and the output says which and why.
// Exit 3: every flow that could run passed, but a key is missing, so some flows (or all) did not run.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';

// Edit these four for the project.
const PORT = 3999;
const START = `npx next dev --port ${PORT}`;
const READY_PATH = '/';
// Keys the core flow cannot work without. A key only one feature needs goes in that flow's `needs`.
const REQUIRED_ENV = [];

const BASE = `http://localhost:${PORT}`;
// A cold dev server compiles on first request; real model calls can take a while.
const STARTUP_TIMEOUT_MS = 90000;
const REQUEST_TIMEOUT_MS = 60000;

/**
 * One entry per acceptance item in .work/plan.md: what a judge does, and what must come back.
 * Check real content (the values the spec promises), not just a 200. A flow with `needs` runs only
 * when those keys are set; the core flows run without them, which proves a missing key for one
 * feature cannot take the core result down.
 */
const FLOWS = [
  {
    name: 'A1 analyse a posting',
    async run() {
      const { status, text, body } = await call('POST', '/api/analyse', { posting: 'Senior React engineer. Must know TypeScript, GraphQL and AWS.' });
      expect(status === 200, `status ${status}: ${text.slice(0, 300)}`);
      expect(Array.isArray(body?.skills) && body.skills.length > 0, `no skills in ${text.slice(0, 300)}`);
      expect(body.skills.some((skill) => /graphql/i.test(skill.name)), 'GraphQL, named in the posting, is missing');
    },
  },
  {
    name: 'A2 summarise the gaps',
    needs: ['OPENAI_API_KEY'],
    async run() {
      const { status, text, body } = await call('POST', '/api/summary', { skills: ['GraphQL'] });
      expect(status === 200, `status ${status}: ${text.slice(0, 300)}`);
      expect(typeof body?.summary === 'string' && body.summary.length > 20, `no summary in ${text.slice(0, 300)}`);
    },
  },
];

/** Fails the current flow with a message saying what was wrong. */
function expect(condition, message) {
  if (!condition) throw new Error(message);
}

/**
 * Calls the running app, with a timeout so a hung call fails instead of waiting. Returns the status,
 * the raw text (for error messages) and the parsed JSON body, or null when it is not JSON.
 */
async function call(method, urlPath, payload) {
  const response = await fetch(`${BASE}${urlPath}`, {
    method,
    headers: payload === undefined ? {} : { 'content-type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  const text = await response.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    // An HTML error page or plain text: the flow's checks report it through `text`.
  }
  return { status: response.status, text, body };
}

/** Loads .env into the environment when present, the same way the app reads it. */
function loadEnv() {
  if (fs.existsSync('.env')) process.loadEnvFile('.env');
}

/** Starts the app in its own process group, so stopping it also stops what it spawned. */
function startApp() {
  const app = spawn(START, { shell: true, detached: process.platform !== 'win32', stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  const keep = (chunk) => {
    log = `${log}${chunk}`.slice(-4000);
  };
  app.stdout.on('data', keep);
  app.stderr.on('data', keep);
  return { app, log: () => log };
}

/** Stops the app and everything it started. */
function stopApp(app) {
  if (app.exitCode !== null) return;
  if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(app.pid), '/T', '/F']);
  else process.kill(-app.pid, 'SIGTERM');
}

/** Waits until the app answers, or fails with its own log when it never does. */
async function waitUntilReady(app, log) {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (app.exitCode !== null) throw new Error(`the app exited with ${app.exitCode} before it was ready:\n${log()}`);
    try {
      const response = await fetch(`${BASE}${READY_PATH}`, { signal: AbortSignal.timeout(5000) });
      if (response.status < 500) return;
    } catch {
      // Not listening yet: keep polling until the deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`the app did not answer on ${BASE}${READY_PATH} within ${STARTUP_TIMEOUT_MS / 1000} s:\n${log()}`);
}

/** Runs every flow whose keys are set and prints one line each; returns the failed and skipped counts. */
async function runFlows() {
  let failures = 0;
  let skipped = 0;
  for (const flow of FLOWS) {
    const missing = (flow.needs ?? []).filter((name) => !process.env[name]);
    if (missing.length > 0) {
      skipped += 1;
      console.log(`skip  ${flow.name}: set ${missing.join(', ')} to run it`);
      continue;
    }
    const started = Date.now();
    try {
      await flow.run();
      console.log(`ok    ${flow.name} (${Date.now() - started} ms)`);
    } catch (error) {
      failures += 1;
      console.log(`FAIL  ${flow.name}: ${error.message}`);
    }
  }
  return { failures, skipped };
}

/** Checks the environment, starts the app, runs the flows, and always stops the app. */
async function main() {
  loadEnv();
  const missing = REQUIRED_ENV.filter((name) => !process.env[name]);
  if (missing.length > 0) {
    console.log(`cannot run: set ${missing.join(', ')} in .env (see .env.example)`);
    process.exit(3);
  }
  const { app, log } = startApp();
  try {
    await waitUntilReady(app, log);
    const { failures, skipped } = await runFlows();
    const ran = FLOWS.length - skipped;
    if (failures > 0) console.log(`smoke: ${failures} of ${ran} flows failed`);
    else if (skipped > 0) console.log(`smoke: ${ran} flows passed, ${skipped} not run for a missing key`);
    else console.log(`smoke: all ${ran} flows passed`);
    process.exitCode = failures > 0 ? 1 : skipped > 0 ? 3 : 0;
  } catch (error) {
    console.log(`FAIL  ${error.message}`);
    process.exitCode = 1;
  } finally {
    stopApp(app);
  }
}

await main();

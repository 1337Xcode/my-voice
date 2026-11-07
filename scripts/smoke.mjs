// Smoke check: runs every demo flow built so far against the deployed speech server, checking the
// content that comes back. Exit 0 all passed, 1 a flow failed, 3 a key is missing (named below).
// The server runs on Modal (GPU), so this checks the deployed app: run `npm run deploy` first.
import fs from 'node:fs';
import { readDotenv } from './dotenv.mjs';

const env = { ...readDotenv('.env'), ...process.env };
const urlFile = '.work/server-url';
const SERVER = (env.SMOKE_SERVER_URL || (fs.existsSync(urlFile) ? fs.readFileSync(urlFile, 'utf8') : '')).trim();
const TOKEN = env.APP_TOKEN;
const FLOW_TIMEOUT_MS = 90_000;

if (!SERVER || !TOKEN) {
  console.log(`MISSING ${!SERVER ? 'server URL (run npm run deploy)' : 'APP_TOKEN in .env'}`);
  process.exit(3);
}

/** Calls a route with the app token and returns { status, body }. */
async function call(path, init = {}) {
  const response = await fetch(`${SERVER}${path}`, { ...init, headers: { Authorization: `Bearer ${TOKEN}`, ...init.headers }, signal: AbortSignal.timeout(FLOW_TIMEOUT_MS) });
  const body = await response.json().catch(() => null);
  return { status: response.status, body };
}

/** Opens /ws, sends the given messages, and resolves with the first message matching `until`. */
function socketExchange(messages, until) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${SERVER.replace('https', 'wss')}/ws?token=${TOKEN}`);
    const timer = setTimeout(() => { ws.close(); reject(new Error('no reply within 90 s')); }, FLOW_TIMEOUT_MS);
    ws.onopen = () => messages.forEach((m) => ws.send(JSON.stringify(m)));
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (until(message)) { clearTimeout(timer); ws.close(); resolve(message); }
    };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('WebSocket error')); };
  });
}

function check(condition, message) {
  if (!condition) throw new Error(message);
}

const FLOWS = [
  {
    name: 'P0 health answers without a token',
    run: async () => {
      const { status, body } = await call('/health', { headers: { Authorization: '' } });
      check(status === 200 && body?.ok === true, `health returned ${status}`);
    },
  },
  {
    name: 'P0 a wrong token is refused',
    run: async () => {
      const response = await fetch(`${SERVER}/wake`, { method: 'POST', headers: { Authorization: 'Bearer wrong' } });
      check(response.status === 401, `wake with a wrong token returned ${response.status}`);
    },
  },
  {
    name: 'P0 hello gets ready with speaker, model and voice',
    run: async () => {
      const started = performance.now();
      const ready = await socketExchange([{ type: 'hello', speaker: 'P1', client_version: 'smoke', settings: {} }], (m) => m.type === 'ready' || m.type === 'error');
      check(ready.type === 'ready', `got ${JSON.stringify(ready)}`);
      check(ready.speaker === 'P1' && typeof ready.model_version === 'string' && ready.voice_id, `ready is missing fields: ${JSON.stringify(ready)}`);
      return `${Math.round(performance.now() - started)} ms to ready`;
    },
  },
  {
    name: 'P0 phrase bank holds the default phrases',
    run: async () => {
      const { status, body } = await call('/phrases?speaker=P1');
      check(status === 200 && Array.isArray(body?.phrases), `phrases returned ${status}`);
      check(body.phrases.some((p) => p.text === 'Can I have a flat white, please?'), 'default phrase missing');
    },
  },
  {
    name: 'P0 state reports the model and clip counts',
    run: async () => {
      const { status, body } = await call('/state?speaker=P1');
      check(status === 200 && typeof body?.model_version === 'string' && typeof body?.clips?.train === 'number', `state returned ${status}: ${JSON.stringify(body)}`);
    },
  },
];

let failed = 0;
let missing = [];
for (const flow of FLOWS) {
  const lacking = (flow.needs ?? []).filter((key) => !env[key]);
  if (lacking.length) {
    missing.push(...lacking);
    console.log(`SKIP ${flow.name} (needs ${lacking.join(', ')})`);
    continue;
  }
  try {
    const note = await flow.run();
    console.log(`PASS ${flow.name}${note ? ` (${note})` : ''}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${flow.name}: ${error.message}`);
  }
}
if (failed) process.exit(1);
if (missing.length) {
  console.log(`MISSING ${[...new Set(missing)].join(', ')}`);
  process.exit(3);
}
console.log('All flows passed.');

// Smoke check: runs every demo flow built so far against the deployed speech server, checking the
// content that comes back. Exit 0 all passed, 1 a flow failed, 3 a key is missing (named below).
// The server runs on Modal (GPU), so this checks the deployed app: run `npm run deploy` first.
import fs from 'node:fs';
import { readDotenv } from './dotenv.mjs';
import { pcmOf, runTurn } from './turn.mjs';

const env = { ...readDotenv('.env'), ...process.env };
const urlFile = '.work/server-url';
const SERVER = (env.SMOKE_SERVER_URL || (fs.existsSync(urlFile) ? fs.readFileSync(urlFile, 'utf8') : '')).trim();
const TOKEN = env.APP_TOKEN;
const FLOW_TIMEOUT_MS = 90_000;
// A real P1 recording from the team data (Harvard list 8 #1), fetched by `modal volume get` into .work/p1/.
const SAMPLE_WAV = '.work/p1/P1_t01.wav';

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
    name: 'P1 a spoken sentence is recognised, decided and voiced',
    needs: ['TYPESAFE_API_KEY', 'ELEVENLABS_API_KEY'],
    run: async () => {
      const outcome = await runTurn(pcmOf(fs.readFileSync(SAMPLE_WAV)), { realtime: false });
      check(outcome.result?.type === 'result', `got ${JSON.stringify(outcome.result)}`);
      check(['speak', 'pick', 'again'].includes(outcome.result.action), `action ${outcome.result.action}`);
      check(outcome.result.candidates.some((c) => /fish/i.test(c.text)), `no candidate mentions the fish: ${JSON.stringify(outcome.result.candidates)}`);
      check(outcome.audioBytes > 5000, 'no voice audio came back');
      return `${outcome.result.action}, text ${outcome.result.ms} ms, voice ${outcome.audioMs} ms`;
    },
  },
  {
    name: 'P1 silence is ignored, never spoken',
    run: async () => {
      const outcome = await runTurn(Buffer.alloc(3200 * 15), { realtime: false, choose: false });
      check(outcome.result?.type === 'ignored', `silence produced ${JSON.stringify(outcome.result)}`);
    },
  },
  {
    name: 'P1 a phrase tap is spoken',
    needs: ['ELEVENLABS_API_KEY'],
    run: async () => {
      const audio = await socketExchange([{ type: 'hello', speaker: 'P1', client_version: 'smoke', settings: {} }, { type: 'say_phrase', phrase_id: 'p02' }], (m) => m.type === 'audio' || m.type === 'error');
      check(audio.type === 'audio' && audio.phrase_id === 'p02' && audio.data.length > 1000, `got ${JSON.stringify(audio).slice(0, 200)}`);
    },
  },
  {
    name: 'P2 Teach offers the next prompt',
    run: async () => {
      const { status, body } = await call('/teach/next?speaker=P1');
      check(status === 200 && ['phrase', 'harvard', 'done'].includes(body?.prompt?.kind), `teach/next returned ${status}: ${JSON.stringify(body)}`);
    },
  },
  {
    name: 'P4 Results show stock and his model from real data',
    run: async () => {
      const { status, body } = await call('/results?speaker=P1');
      check(status === 200 && Array.isArray(body?.headline), `results returned ${status}`);
      check(body.headline.some((row) => row.kind === 'stock') && body.headline.some((row) => row.kind === 'model'), `headline rows: ${body.headline.map((r) => r.system)}`);
    },
  },
  {
    name: 'P6 his call link and code are issued',
    run: async () => {
      const { status, body } = await call('/calls/link?speaker=P1', { method: 'POST' });
      check(status === 200 && /^\d{6}$/.test(body?.code ?? ''), `calls/link returned ${status}: ${JSON.stringify(body)}`);
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

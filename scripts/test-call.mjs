// Places one real phone call through the live server as his app would: opens his session, starts the call,
// speaks one sentence once answered, prints every call event with its time, and hangs up.
// Usage: node scripts/test-call.mjs <E.164 number> [speaker] [seconds after answer]
import fs from 'node:fs';
import { readDotenv } from './dotenv.mjs';

const [number, speaker = 'S1', holdSeconds = '30'] = process.argv.slice(2);
if (!number) {
  console.error('Usage: node scripts/test-call.mjs <number> [speaker] [seconds]');
  process.exit(1);
}
const env = readDotenv('.env');
const server = fs.readFileSync('.work/server-url', 'utf8').trim();
const auth = { Authorization: `Bearer ${env.APP_TOKEN}` };
const started = performance.now();
const at = () => `${((performance.now() - started) / 1000).toFixed(1)}s`;
const OPENING_LINE = "Hi, this is a test call from the My Voice speech app. There'll be short pauses.";
const SENTENCE = "Hello, can you hear me clearly? This is the voice I'll use on calls.";

const ws = new WebSocket(`${server.replace('https', 'wss')}/ws?token=${env.APP_TOKEN}`);
let callId = null;
let spokenAt = 0;

async function hangUp(reason) {
  console.log(`${at()} hanging up (${reason})`);
  if (callId) await fetch(`${server}/calls/${callId}/hangup?speaker=${speaker}`, { method: 'POST', headers: auth }).catch(() => undefined);
  setTimeout(() => { ws.close(); process.exit(0); }, 3000);
}

ws.onopen = () => ws.send(JSON.stringify({ type: 'hello', speaker, client_version: 'test-call', settings: {} }));
ws.onmessage = async (event) => {
  const message = JSON.parse(event.data);
  if (message.type === 'ready') {
    console.log(`${at()} session ready (${message.model_version}), placing the call`);
    const response = await fetch(`${server}/calls?speaker=${speaker}`, {
      method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' },
      body: JSON.stringify({ number, name: 'Friend', opening_line: OPENING_LINE }),
    });
    const body = await response.json();
    console.log(`${at()} POST /calls -> ${response.status} ${JSON.stringify(body)}`);
    if (!response.ok) process.exit(1);
    callId = body.call_id;
  } else if (message.type === 'call_status') {
    console.log(`${at()} call_status ${message.state}${message.detail ? ` (${message.detail})` : ''}`);
    if (message.state === 'connected' && !spokenAt) {
      setTimeout(() => {
        spokenAt = performance.now();
        console.log(`${at()} speaking: "${SENTENCE}"`);
        ws.send(JSON.stringify({ type: 'type_and_speak', text: SENTENCE }));
      }, 7000);
      setTimeout(() => hangUp('test finished'), Number(holdSeconds) * 1000);
    }
    if (message.state === 'ended' || message.state === 'failed') setTimeout(() => process.exit(0), 1000);
  } else if (message.type === 'partner_caption') {
    console.log(`${at()} caption from them: "${message.text}"`);
  } else if (message.type === 'audio' && spokenAt) {
    console.log(`${at()} his voice ready ${Math.round(performance.now() - spokenAt)} ms after the request`);
  } else if (message.type === 'error') {
    console.log(`${at()} error ${message.code}: ${message.message}`);
  }
};
setTimeout(() => hangUp('safety timeout'), 120_000);

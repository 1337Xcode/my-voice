// Plays one recording through the live turn pipeline exactly as the app does: 100 ms frames of 16 kHz
// 16-bit PCM over /ws, then Done, then picks the first option and waits for the voice. Prints each stage.
// Usage: node scripts/turn.mjs <16 kHz mono 16-bit wav> [speaker]
import fs from 'node:fs';
import { readDotenv } from './dotenv.mjs';

const [file, speaker = 'P1'] = process.argv.slice(2);
if (!file) {
  console.error('Usage: node scripts/turn.mjs <wav file> [speaker]');
  process.exit(1);
}
const env = { ...readDotenv('.env'), ...process.env };
const server = (env.SMOKE_SERVER_URL || fs.readFileSync('.work/server-url', 'utf8')).trim();
const FRAME_BYTES = 3200; // 100 ms at 16 kHz, 16-bit mono.

/** Returns the PCM payload of a 16 kHz mono 16-bit WAV file. */
export function pcmOf(wav) {
  let offset = 12;
  while (offset < wav.length) {
    const id = wav.toString('ascii', offset, offset + 4);
    const size = wav.readUInt32LE(offset + 4);
    if (id === 'fmt ') {
      const channels = wav.readUInt16LE(offset + 10), rate = wav.readUInt32LE(offset + 12), bits = wav.readUInt16LE(offset + 22);
      if (channels !== 1 || rate !== 16000 || bits !== 16) throw new Error(`need 16 kHz mono 16-bit, got ${rate} Hz ${channels} ch ${bits} bit`);
    }
    if (id === 'data') return wav.subarray(offset + 8, offset + 8 + size);
    offset += 8 + size + (size % 2);
  }
  throw new Error('no data chunk');
}

/** Runs one turn and resolves with { result, audio, ms } once the chosen sentence's audio arrives. */
export function runTurn(pcm, { speaker: spk = speaker, realtime = true, choose = true } = {}) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${server.replace('https', 'wss')}/ws?token=${env.APP_TOKEN}`);
    const turnId = `cli-${Date.now()}`;
    const log = [];
    let doneAt = 0;
    let result = null;
    const timer = setTimeout(() => { ws.close(); reject(new Error(`timed out; got ${log.join(', ')}`)); }, 120_000);
    ws.onopen = () => ws.send(JSON.stringify({ type: 'hello', speaker: spk, client_version: 'cli', settings: {} }));
    ws.onmessage = async (event) => {
      const message = JSON.parse(event.data);
      log.push(message.type);
      if (message.type === 'ready') {
        ws.send(JSON.stringify({ type: 'start_turn', turn_id: turnId, mode: 'talk' }));
        for (let i = 0; i < pcm.length; i += FRAME_BYTES) {
          ws.send(pcm.subarray(i, i + FRAME_BYTES));
          if (realtime) await new Promise((r) => setTimeout(r, 100));
        }
        doneAt = performance.now();
        ws.send(JSON.stringify({ type: 'end_turn', turn_id: turnId }));
      } else if (message.type === 'result') {
        result = { ...message, ms: Math.round(performance.now() - doneAt) };
        if (!choose) { clearTimeout(timer); ws.close(); resolve({ result }); return; }
        if (!message.candidates.length || message.action === 'speak') return;
        ws.send(JSON.stringify({ type: 'choose', turn_id: turnId, candidate_id: message.candidates[0].id, via: 'pick' }));
      } else if (message.type === 'audio') {
        clearTimeout(timer);
        ws.close();
        resolve({ result, audioBytes: Buffer.from(message.data, 'base64').length, audioMs: Math.round(performance.now() - doneAt) });
      } else if (message.type === 'ignored' || message.type === 'error') {
        clearTimeout(timer);
        ws.close();
        resolve({ result: message });
      }
    };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('WebSocket error')); };
  });
}

if (import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/').split('/').pop())) {
  const outcome = await runTurn(pcmOf(fs.readFileSync(file)));
  console.log(JSON.stringify(outcome, null, 2));
}

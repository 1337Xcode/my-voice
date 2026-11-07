// Times the app's WebSocket handshake (hello -> ready) against the deployed server.
import fs from 'node:fs';
import { readDotenv } from './dotenv.mjs';
const url = fs.readFileSync('.work/server-url', 'utf8').trim();
const token = readDotenv('.env').APP_TOKEN;
const started = performance.now();
const ws = new WebSocket(`${url.replace('https', 'wss')}/ws?token=${token}`);
const timer = setTimeout(() => { console.log('TIMEOUT after 90s'); process.exit(1); }, 90000);
ws.onopen = () => ws.send(JSON.stringify({ type: 'hello', speaker: 'P1', client_version: 'cli', settings: {} }));
ws.onmessage = (e) => { console.log(`${Math.round(performance.now() - started)} ms`, e.data); clearTimeout(timer); ws.close(); };
ws.onerror = (e) => { console.log('error', e.message); process.exit(1); };

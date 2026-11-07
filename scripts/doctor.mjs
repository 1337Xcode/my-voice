// Checks every key in .env against its real service with one small call, printing only pass/fail
// and the service's error message, never a key. Run: npm run doctor
import { readDotenv } from './dotenv.mjs';

const env = readDotenv('.env');
const TIMEOUT_MS = 20_000;

/** Calls a URL and returns { status, body } (body parsed as JSON when it can be). */
async function request(url, init = {}) {
  const response = await fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  const text = await response.text();
  let body = text;
  try { body = JSON.parse(text); } catch { /* keep text */ }
  return { status: response.status, body };
}

const CHECKS = [
  {
    name: 'Anthropic (claude-haiku-5-5)',
    needs: ['ANTHROPIC_API_KEY'],
    run: () => request('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
      body: JSON.stringify({ model: 'claude-haiku-5-5', max_tokens: 5, messages: [{ role: 'user', content: 'Say ok.' }] }),
    }),
  },
  {
    name: 'OpenAI (models list on OPENAI_BASE_URL)',
    needs: ['OPENAI_API_KEY'],
    run: () => request(`${env.OPENAI_BASE_URL || 'https://api.openai.com/v1'}/models/${env.PARSE_MODEL || 'gpt-6-luna'}`, { headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}` } }),
  },
  {
    name: 'TypeSafe AI (Jev models list)',
    needs: ['TYPESAFE_API_KEY'],
    run: () => request('https://api.typesafe.ai/v1/models', { headers: { Authorization: `Bearer ${env.TYPESAFE_API_KEY}` } }),
  },
  {
    name: 'ElevenLabs (default voice)',
    needs: ['ELEVENLABS_API_KEY', 'ELEVENLABS_VOICE_ID'],
    run: () => request(`https://api.elevenlabs.io/v1/voices/${env.ELEVENLABS_VOICE_ID}`, { headers: { 'xi-api-key': env.ELEVENLABS_API_KEY } }),
  },
  {
    name: 'Twilio (account)',
    needs: ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'],
    run: () => request(`https://api.twilio.com/2010-04-01/Accounts/${env.TWILIO_ACCOUNT_SID}.json`, { headers: { Authorization: `Basic ${Buffer.from(`${env.TWILIO_ACCOUNT_SID}:${env.TWILIO_AUTH_TOKEN}`).toString('base64')}` } }),
  },
  {
    name: 'Toolkit (getProfile)',
    needs: ['TOOLKIT_URL', 'TOOLKIT_TOKEN'],
    run: () => request(`${env.TOOLKIT_URL}/v1/librarian/getProfile`, { method: 'POST', headers: { Authorization: `Bearer ${env.TOOLKIT_TOKEN}`, 'content-type': 'application/json' }, body: JSON.stringify({ args: [] }) }),
  },
];

/** A short, key-free description of what came back. */
function summary(body) {
  if (typeof body !== 'object' || body === null) return String(body).slice(0, 160);
  const error = body.error?.message ?? body.error ?? body.detail?.message ?? body.detail ?? body.message;
  if (error) return `error: ${typeof error === 'string' ? error : JSON.stringify(error)}`.slice(0, 200);
  if (body.data && Array.isArray(body.data)) return `ok: ${body.data.map((m) => m.id ?? m.name).slice(0, 6).join(', ')}`;
  if (body.name && body.voice_id) return `ok: voice "${body.name}" (${[body.labels?.gender, body.labels?.age, body.labels?.accent].filter(Boolean).join(', ')})`;
  if (body.id) return `ok: ${body.id}`;
  if (body.content) return 'ok: model answered';
  return 'ok';
}

let failed = 0;
for (const check of CHECKS) {
  const missing = check.needs.filter((key) => !env[key]);
  if (missing.length) { console.log(`MISSING ${check.name}: set ${missing.join(', ')}`); continue; }
  try {
    const { status, body } = await check.run();
    const ok = status >= 200 && status < 300;
    if (!ok) failed += 1;
    console.log(`${ok ? 'PASS' : 'FAIL'} ${check.name}: HTTP ${status} ${summary(body)}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${check.name}: ${error.message}`);
  }
}
process.exit(failed ? 1 : 0);

// Deploys the speech server: syncs .env into the Modal secret, deploys the Modal app, then writes
// the app's public env (app/.env) with the server URL and token so the phone build can reach it.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readDotenv } from './dotenv.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SECRET_NAME = 'my-voice-env';

/** Runs a command, streaming its output, and returns its stdout. Exits on failure. */
function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: root, encoding: 'utf8', shell: process.platform === 'win32', ...options });
  process.stdout.write(result.stdout ?? '');
  process.stderr.write(result.stderr ?? '');
  if (result.status !== 0) {
    console.error(`\n${command} ${args[0]} failed with exit code ${result.status}.`);
    process.exit(result.status ?? 1);
  }
  return result.stdout ?? '';
}

const envFile = path.join(root, '.env');
if (!fs.existsSync(envFile)) {
  console.error('No .env at the repo root. Copy .env.example to .env and fill it in.');
  process.exit(1);
}
const env = readDotenv(envFile);
if (!env.APP_TOKEN) {
  console.error('APP_TOKEN is empty in .env. Set it to any long random string.');
  process.exit(1);
}

// Only non-empty values go into the secret, so an unset key reads as missing on the server.
const filled = path.join(root, '.work', 'secret.env');
fs.mkdirSync(path.dirname(filled), { recursive: true });
fs.writeFileSync(filled, Object.entries(env).filter(([, v]) => v !== '').map(([k, v]) => `${k}=${v}`).join('\n') + '\n');
run('modal', ['secret', 'create', SECRET_NAME, '--from-dotenv', filled, '--force']);
fs.rmSync(filled);

const output = run('modal', ['deploy', 'main.py'], { cwd: path.join(root, 'server'), env: { ...process.env, KEEP_WARM: env.KEEP_WARM ?? '0', PYTHONIOENCODING: 'utf-8' } });
const url = /https:\/\/[\w.-]+\.modal\.run/.exec(output)?.[0];
if (!url) {
  console.error('Deployed, but could not find the web URL in the output above.');
  process.exit(1);
}

// With max_containers=1, an old container kept busy by an open WebSocket would block the new version
// until its sessions end, so stop it: apps reconnect with backoff and land on the new container.
const listed = spawnSync('modal', ['container', 'list', '--json'], { cwd: root, encoding: 'utf8', shell: process.platform === 'win32', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
for (const container of JSON.parse(listed.stdout || '[]')) {
  // Containers running right after the deploy finished were started by the previous version.
  const id = container.container_id;
  if (id && container.app_name === 'my-voice') {
    spawnSync('modal', ['container', 'stop', id, '--yes'], { cwd: root, shell: process.platform === 'win32' });
    console.log(`Stopped the previous container ${id} so the new version starts.`);
  }
}

const appEnv = {
  EXPO_PUBLIC_SERVER_URL: url,
  EXPO_PUBLIC_APP_TOKEN: env.APP_TOKEN,
  EXPO_PUBLIC_TOOLKIT_URL: env.TOOLKIT_URL ?? '',
  EXPO_PUBLIC_TOOLKIT_TOKEN: env.TOOLKIT_TOKEN ?? '',
};
fs.writeFileSync(path.join(root, 'app', '.env'), Object.entries(appEnv).map(([k, v]) => `${k}=${v}`).join('\n') + '\n');
fs.writeFileSync(path.join(root, '.work', 'server-url'), url);
console.log(`\nServer: ${url}\nWrote app/.env with the server URL and token.`);

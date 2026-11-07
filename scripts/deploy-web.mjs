// Builds the web app without any secret token and deploys it to Vercel as a single-page app.
// Usage: npm run deploy:web [-- <project-name>]   (default project: trymyvoice → https://trymyvoice.vercel.app; myvoice.vercel.app is taken)
// Needs the Vercel token in .work/vercel-token (never printed) and the server URL in app/.env.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { readDotenv } from './dotenv.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const appDir = path.join(root, 'app');
const project = process.argv[2] ?? 'trymyvoice';
const webUrl = (process.env.WEB_URL ?? `https://${project}.vercel.app`).replace(/\/$/, '');
const outDir = path.join(root, '.work', 'web-dist');

/** Stops with a message naming what is missing. */
function fail(message) {
  console.error(`deploy:web: ${message}`);
  process.exit(1);
}

const tokenFile = path.join(root, '.work', 'vercel-token');
if (!fs.existsSync(tokenFile)) fail('put the Vercel token in .work/vercel-token');
const vercelToken = fs.readFileSync(tokenFile, 'utf8').trim();
const appEnv = fs.existsSync(path.join(appDir, '.env')) ? readDotenv(path.join(appDir, '.env')) : {};
const serverUrl = process.env.EXPO_PUBLIC_SERVER_URL || appEnv.EXPO_PUBLIC_SERVER_URL;
if (!serverUrl) fail('EXPO_PUBLIC_SERVER_URL is not set (run npm run deploy first, which writes app/.env)');

// 1. Export. Empty values here win over app/.env, so no token reaches the public bundle;
//    the app asks for an access code instead.
console.log(`Exporting the web app for ${webUrl} …`);
fs.rmSync(outDir, { recursive: true, force: true });
const exported = spawnSync('npx', ['expo', 'export', '-p', 'web', '--output-dir', outDir], {
  cwd: appDir,
  stdio: 'inherit',
  shell: true,
  env: { ...process.env, EXPO_PUBLIC_SERVER_URL: serverUrl, EXPO_PUBLIC_WEB_URL: webUrl, EXPO_PUBLIC_APP_TOKEN: '', EXPO_PUBLIC_TOOLKIT_TOKEN: '', EXPO_PUBLIC_DEFAULT_SPEAKER: process.env.EXPO_PUBLIC_DEFAULT_SPEAKER || 'S1' },
});
if (exported.status !== 0) fail('expo export failed');

// 2. Refuse to publish a bundle that contains a secret.
const secrets = [appEnv.EXPO_PUBLIC_APP_TOKEN, appEnv.EXPO_PUBLIC_TOOLKIT_TOKEN, vercelToken].filter((s) => s && s.length >= 8);
for (const file of fs.readdirSync(outDir, { recursive: true })) {
  const full = path.join(outDir, String(file));
  if (!fs.statSync(full).isFile()) continue;
  const text = fs.readFileSync(full, 'latin1');
  if (secrets.some((secret) => text.includes(secret))) fail(`a secret token is in ${file}; not deploying`);
}

// 3. Vercel never uploads folders named node_modules, but Expo puts fonts and icons under assets/node_modules/;
//    ship them as assets/nm/ and map the old paths onto it.
const moduleAssets = path.join(outDir, 'assets', 'node_modules');
if (fs.existsSync(moduleAssets)) fs.renameSync(moduleAssets, path.join(outDir, 'assets', 'nm'));
// Every other path (deep links such as /c/123456 and /settings) serves the single page; real files still win.
const rewrites = [
  { source: '/assets/node_modules/:path*', destination: '/assets/nm/:path*' },
  { source: '/(.*)', destination: '/' },
];
fs.writeFileSync(path.join(outDir, 'vercel.json'), JSON.stringify({ cleanUrls: true, rewrites }, null, 2));

// 4. Deploy to production.
console.log(`Deploying to Vercel project "${project}" …`);
const deployed = spawnSync('npx', ['--yes', 'vercel@latest', 'deploy', outDir, '--prod', '--yes', '--project', project, '--create-if-missing', '--token', vercelToken], {
  cwd: root,
  encoding: 'utf8',
  shell: true,
});
const output = `${deployed.stdout ?? ''}\n${deployed.stderr ?? ''}`.replaceAll(vercelToken, '***');
console.log(output.trim());
if (deployed.status !== 0) fail('vercel deploy failed');
// Vercel gives <project>.vercel.app only when that name is free; otherwise the baked-in link would be wrong.
const aliased = /Aliased\s+(https:\/\/\S+)/.exec(output)?.[1];
if (aliased && aliased !== webUrl) fail(`${webUrl} is taken (Vercel used ${aliased}); deploy under another name: npm run deploy:web -- <name>`);
console.log(`\nWeb app: ${webUrl}`);

// Tests for the kit's hook: the rules as functions, then the script end to end with the payloads
// Claude Code and Devin actually send. Run from the kit folder: node --test tests/
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  codeState,
  commitMessageProblem,
  commitMessages,
  destructiveProblem,
  editedFiles,
  editNotes,
  isSecretFile,
  reviewCommand,
  reviewStop,
  smokeCommand,
} from '../.claude/hooks/kit.mjs';

const HOOK = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '.claude', 'hooks', 'kit.mjs');
const created = [];
after(() => {
  for (const dir of created) fs.rmSync(dir, { recursive: true, force: true });
});

/** A throwaway git repository with the given files, committed or left untracked; removed after the run. */
function repo(files = {}, { commit = true } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kit-test-'));
  created.push(dir);
  const run = (...args) => spawnSync('git', args, { cwd: dir, encoding: 'utf8' });
  run('init', '-q');
  run('config', 'user.email', 'test@example.com');
  run('config', 'user.name', 'test');
  for (const [file, content] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, file)), { recursive: true });
    fs.writeFileSync(path.join(dir, file), content);
  }
  if (commit && Object.keys(files).length > 0) {
    run('add', '-A');
    run('commit', '-q', '-m', 'chore: start');
  }
  return dir;
}

/** Runs the hook script with one payload, as either agent would. */
function hook(dir, payload, env = {}) {
  const result = spawnSync('node', [HOOK], {
    cwd: dir,
    input: JSON.stringify(payload),
    encoding: 'utf8',
    env: { ...process.env, CLAUDE_PROJECT_DIR: dir, ...env },
  });
  return { code: result.status, stdout: result.stdout, stderr: result.stderr };
}

describe('secret files', () => {
  it('knows env files, keys and credential files, and lets examples through', () => {
    for (const file of ['.env', '.env.local', 'apps/api/.env.production', 'server.pem', 'id_ed25519', 'credentials.json']) {
      assert.equal(isSecretFile(file), true, file);
    }
    for (const file of ['.env.example', '.env.sample', 'id_ed25519.pub', 'src/env.ts', 'keyboard.tsx']) {
      assert.equal(isSecretFile(file), false, file);
    }
  });

  it('refuses staging an unignored .env with git add -A, and allows it once ignored', () => {
    const dir = repo({ 'index.js': 'console.log(1);\n' });
    fs.writeFileSync(path.join(dir, '.env'), 'OPENAI_API_KEY=sk-test\n');
    assert.match(reviewCommand('git add -A && git commit -m "feat: x"', dir), /\.env holds secrets/);
    assert.match(reviewCommand('git add .env', dir), /\.env holds secrets/);
    assert.equal(reviewCommand('git add index.js', dir), null);
    fs.writeFileSync(path.join(dir, '.gitignore'), '.env\n');
    assert.equal(reviewCommand('git add -A', dir), null);
  });

  it('refuses committing a secret that is already staged', () => {
    const dir = repo({ 'index.js': '1\n' });
    fs.writeFileSync(path.join(dir, '.env.local'), 'KEY=1\n');
    spawnSync('git', ['add', '.env.local'], { cwd: dir });
    assert.match(reviewCommand('git commit -m "feat: add key"', dir), /git rm --cached \.env\.local/);
  });
});

describe('commit messages', () => {
  it('reads -m, -am, --message, heredocs and PowerShell here-strings', () => {
    assert.deepEqual(commitMessages('git commit -m "feat(ui): add search"'), ['feat(ui): add search']);
    assert.deepEqual(commitMessages("git commit -am 'fix: crash'"), ['fix: crash']);
    assert.deepEqual(commitMessages('git commit --message=chore:x'), ['chore:x']);
    const heredoc = "git commit -m \"$(cat <<'EOF'\nfeat: stream answers\n\nBody line.\nEOF\n)\"";
    assert.deepEqual(commitMessages(heredoc), ['feat: stream answers\n\nBody line.']);
    assert.deepEqual(commitMessages("git commit -m @'\nfix: retry on 429\n'@"), ['fix: retry on 429']);
    assert.equal(commitMessages('git commit'), null);
    assert.deepEqual(commitMessages('git status'), []);
  });

  it('wants type(scope): summary under 72 characters and no AI attribution', () => {
    assert.equal(commitMessageProblem('feat(search): rank results by distance'), null);
    assert.equal(commitMessageProblem('fix!: drop the old endpoint'), null);
    assert.match(commitMessageProblem('Added search'), /type\(scope\): summary/);
    assert.match(commitMessageProblem(`feat: ${'x'.repeat(80)}`), /at most 72/);
    assert.match(commitMessageProblem('feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>'), /no AI attribution/);
    assert.match(commitMessageProblem('feat: x\n\nGenerated with Devin'), /no AI attribution/);
  });
});

describe('destructive commands', () => {
  it('refuses force pushes, skipped hooks, discarded work and broad deletes', () => {
    for (const command of [
      'git push --force origin main',
      'git push -f',
      'git push origin +main',
      'git commit --no-verify -m "feat: x"',
      'git reset --hard HEAD~1',
      'git clean -fd',
      'git checkout -- .',
      'git restore .',
      'git stash drop',
      'rm -rf /',
      'rm -rf ~',
      'rm -rf .',
    ]) {
      assert.notEqual(destructiveProblem(command), null, command);
    }
  });

  it('lets ordinary work through', () => {
    for (const command of ['git push origin main', 'git restore src/app.tsx', 'rm -rf node_modules .next', 'git reset HEAD file.ts', 'git stash push -m wip']) {
      assert.equal(destructiveProblem(command), null, command);
    }
  });
});

describe('edit checks', () => {
  it('finds the files in a Claude edit and in a Devin patch', () => {
    assert.deepEqual(editedFiles({ file_path: '/repo/app/page.tsx' }), ['/repo/app/page.tsx']);
    const patch = '*** Begin Patch\n*** Add File: C:/repo/a.tsx\n+x\n*** Update File: C:/repo/b.ts\n@@\n-y\n+z\n*** End Patch\n';
    assert.deepEqual(editedFiles(patch), ['C:/repo/a.tsx', 'C:/repo/b.ts']);
  });

  it('notes fake modes, demo copy and generated-UI styling, with line numbers', () => {
    const page = [
      'import { Inter } from "next/font/google";',
      'const USE_MOCK_DATA = true;',
      '<div className="bg-gradient-to-r from-violet-500 to-indigo-600">',
      '<span>Demo</span>',
      '<h1>Welcome 🚀</h1>',
    ].join('\n');
    const ids = editNotes('app/page.tsx', page).map((hit) => `${hit.id}@${hit.lines.join(',')}`);
    assert.deepEqual(ids, ['fake-mode@2', 'placeholder-copy@4', 'ai-palette@3', 'gradient@3', 'emoji@5', 'font@1']);
  });

  it('leaves tests, scripts, kit files and library components alone, and plain code clean', () => {
    assert.deepEqual(editNotes('app/page.test.tsx', 'const mockData = 1;'), []);
    assert.deepEqual(editNotes('scripts/smoke.mjs', 'const mockData = 1;'), []);
    assert.deepEqual(editNotes('components/ui/skeleton.tsx', 'animate-pulse'), []);
    assert.deepEqual(editNotes('app/page.tsx', '<main className="bg-background text-foreground">'), []);
    assert.deepEqual(editNotes('components/week.tsx', '<div className="h-4 animate-pulse rounded bg-muted" />'), []);
  });
});

describe('smoke command', () => {
  it('uses the package script with the lockfile runner, then scripts/smoke.mjs or .py', () => {
    const node = repo({ 'package.json': '{"scripts":{"smoke":"node smoke.mjs"}}', 'pnpm-lock.yaml': '' });
    assert.equal(smokeCommand(node), 'pnpm run smoke');
    assert.equal(smokeCommand(repo({ 'pyproject.toml': '', 'scripts/smoke.mjs': '' })), 'node scripts/smoke.mjs');
    const python = repo({ 'scripts/smoke.py': 'print(1)', 'uv.lock': '' });
    assert.equal(smokeCommand(python), 'uv run python scripts/smoke.py');
    assert.equal(smokeCommand(repo({ 'README.md': 'x' })), null);
  });

  it('changes the code state when a file changes and not when kit state does', () => {
    const dir = repo({ 'index.js': '1\n' });
    const before = codeState(dir);
    fs.mkdirSync(path.join(dir, '.work'), { recursive: true });
    fs.writeFileSync(path.join(dir, '.work', 'plan.md'), 'notes');
    assert.equal(codeState(dir), before);
    fs.writeFileSync(path.join(dir, 'index.js'), '2\n');
    assert.notEqual(codeState(dir), before);
  });
});

describe('end of turn', () => {
  const passing = async () => ({ code: 0, output: 'ok', timedOut: false });
  const failing = async () => ({ code: 1, output: 'search returned 500', timedOut: false });

  it('asks once per session for a smoke check when there is code and none exists', async () => {
    const dir = repo({ 'app/page.tsx': 'export default 1;\n' });
    assert.match((await reviewStop(dir, 's1', passing)).reason, /no smoke check yet/);
    assert.equal(await reviewStop(dir, 's1', passing), null);
  });

  it('says nothing when the repository holds only the kit', async () => {
    assert.equal(await reviewStop(repo({ 'AGENTS.md': '# x' }), 's1', passing), null);
  });

  it('keeps the agent working while the smoke fails, twice per state, then lets it end', async () => {
    const dir = repo({ 'package.json': '{"scripts":{"smoke":"x"}}', 'index.js': '1\n' });
    assert.match((await reviewStop(dir, 's', failing)).reason, /exited 1[\s\S]*search returned 500/);
    assert.equal((await reviewStop(dir, 's', failing)).block, true);
    assert.match((await reviewStop(dir, 's', failing)).warning, /still failing/);
    assert.equal(await reviewStop(dir, 's', failing), null);
  });

  it('runs again only after the code changes, and stops asking after a pass', async () => {
    const dir = repo({ 'package.json': '{"scripts":{"smoke":"x"}}', 'index.js': '1\n' });
    let runs = 0;
    const counted = async () => {
      runs += 1;
      return { code: 0, output: '', timedOut: false };
    };
    assert.equal(await reviewStop(dir, 's', counted), null);
    assert.equal(await reviewStop(dir, 's', counted), null);
    assert.equal(runs, 1);
    fs.writeFileSync(path.join(dir, 'index.js'), '2\n');
    await reviewStop(dir, 's', counted);
    assert.equal(runs, 2);
  });

  it('treats exit 3 as "cannot run here" and warns instead of blocking', async () => {
    const dir = repo({ 'package.json': '{"scripts":{"smoke":"x"}}', 'index.js': '1\n' });
    const unconfigured = async () => ({ code: 3, output: 'OPENAI_API_KEY is not set', timedOut: false });
    assert.match((await reviewStop(dir, 's', unconfigured)).warning, /OPENAI_API_KEY/);
  });
});

describe('the hook script, as each agent calls it', () => {
  it('blocks a bad Claude Bash commit with exit 2 and the reason on stderr', () => {
    const dir = repo({ 'index.js': '1\n' });
    const result = hook(dir, { hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: 'git commit -m "stuff"' } });
    assert.equal(result.code, 2);
    assert.match(result.stderr, /type\(scope\): summary/);
  });

  it('blocks the same command from Devin, which sends exec with a workdir', () => {
    const dir = repo({ 'index.js': '1\n' });
    const result = hook(dir, { hook_event_name: 'PreToolUse', tool_name: 'exec', tool_input: { command: 'git push --force', workdir: dir } }, { CLAUDE_PROJECT_DIR: '', DEVIN_PROJECT_DIR: dir });
    assert.equal(result.code, 2);
    assert.match(result.stderr, /Force pushes/);
  });

  it('lets an ordinary command through silently', () => {
    const result = hook(repo({ 'index.js': '1\n' }), { hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: 'npm test' } });
    assert.deepEqual([result.code, result.stdout, result.stderr], [0, '', '']);
  });

  it('adds a note after a Devin apply_patch edit, once', () => {
    const dir = repo({ 'index.js': '1\n' });
    const file = path.join(dir, 'app', 'page.tsx').replace(/\\/g, '/');
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, '<div className="text-violet-600">Coming soon</div>\n');
    const payload = { hook_event_name: 'PostToolUse', tool_name: 'apply_patch', tool_input: `*** Begin Patch\n*** Add File: ${file}\n+x\n*** End Patch\n`, tool_response: { success: true } };
    const first = hook(dir, payload);
    const context = JSON.parse(first.stdout).hookSpecificOutput.additionalContext;
    assert.match(context, /app\/page\.tsx:1: placeholder/);
    assert.match(context, /violet/);
    assert.equal(hook(dir, payload).stdout, '');
  });

  it('fails open on a payload it cannot parse', () => {
    const result = spawnSync('node', [HOOK], { input: 'not json', encoding: 'utf8' });
    assert.equal(result.status, 0);
    assert.match(result.stderr, /ignored/);
  });

  it('runs the real smoke script at Stop and blocks while it fails', () => {
    const dir = repo({ 'package.json': '{"scripts":{"smoke":"node smoke.mjs"}}', 'smoke.mjs': 'console.error("POST /api/rank returned 500"); process.exit(1);\n', 'index.js': '1\n' });
    const result = hook(dir, { hook_event_name: 'Stop', stop_hook_active: false, session_id: 's' });
    assert.equal(result.code, 2);
    assert.match(result.stderr, /npm run smoke[\s\S]*returned 500/);
  });
});

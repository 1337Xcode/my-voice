// The hackathon kit's one hook. Claude Code runs it from .claude/settings.json, and Devin runs the
// same entries because it imports Claude Code hooks, so it reads both agents' payloads:
//   PreToolUse on a shell command: refuses committing secrets, AI attribution or a malformed
//     subject, skipping git hooks, force pushes, and commands that throw away uncommitted work.
//   PostToolUse on a file edit: notes once the patterns that make a build fake or sloppy.
//   Stop: runs the project's smoke check when the code changed since it last passed, and keeps the
//     agent working while it fails, a bounded number of times.
// Nothing else is blocked. An error inside this script never stops the agent: it fails open.

import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const SHELL_TOOLS = new Set(['Bash', 'PowerShell', 'exec']);
const EDIT_TOOLS = new Set(['Write', 'Edit', 'MultiEdit', 'write', 'edit', 'apply_patch']);
const COMMIT_TYPES = 'feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert';
const SUBJECT = new RegExp(`^(${COMMIT_TYPES})(\\([\\w ./,-]+\\))?!?: \\S`);
const MAX_SUBJECT_CHARS = 72;
// A smoke run must start the app, check it and stop it; anything slower is a hung server.
const SMOKE_TIMEOUT_MS = Number(process.env.KIT_SMOKE_TIMEOUT_S ?? 240) * 1000;
// Exit code a smoke check uses to say it cannot run here (a key or service is missing).
const SMOKE_NOT_CONFIGURED = 3;
// Stops per identical state of the code, and in a row without a pass, before the agent may end.
const MAX_STOPS_PER_STATE = 2;
const MAX_STOPS_IN_A_ROW = 4;

/** Where the project is: both agents set CLAUDE_PROJECT_DIR, Devin also sets its own. */
export function projectRoot(env = process.env) {
  return env.CLAUDE_PROJECT_DIR || env.DEVIN_PROJECT_DIR || process.cwd();
}

/** The kit's state folder, which ignores itself so it is never committed. */
function stateDir(root) {
  const dir = path.join(root, '.work', '.kit');
  fs.mkdirSync(dir, { recursive: true });
  const ignore = path.join(root, '.work', '.gitignore');
  if (!fs.existsSync(ignore)) fs.writeFileSync(ignore, '*\n');
  return dir;
}

/** Reads one JSON state file, or the fallback when it is missing or unreadable. */
function readState(root, name, fallback) {
  try {
    return JSON.parse(fs.readFileSync(path.join(stateDir(root), name), 'utf8'));
  } catch {
    // No state yet, or a half-written file from a killed run: start over.
    return fallback;
  }
}

/** Writes one JSON state file. */
function writeState(root, name, value) {
  fs.writeFileSync(path.join(stateDir(root), name), `${JSON.stringify(value, null, 2)}\n`);
}

/** Runs git and returns its output, or null when git fails or this is not a repository. */
function git(cwd, args) {
  const result = spawnSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  return result.status === 0 ? result.stdout : null;
}

// Shell commands: what may not run.

/** True for files that hold secrets: env files other than the example, keys and credential files. */
export function isSecretFile(file) {
  const name = path.basename(file.replace(/\\/g, '/'));
  if (/^\.env(\..+)?$/.test(name)) return !/\.(example|sample|template|defaults?)$/.test(name);
  if (/\.(pem|key|p12|pfx|keystore|jks)$/i.test(name)) return true;
  return /^(id_rsa|id_ed25519|id_ecdsa|credentials\.json|service-account.*\.json)$/i.test(name);
}

/** The text of each git commit message in a command, or null when it opens an editor or a file. */
export function commitMessages(command) {
  if (!/\bgit\b[^\n]*\bcommit\b/.test(command)) return [];
  const heredoc = /<<-?\s*['"]?([A-Za-z_]+)['"]?[^\n]*\n([\s\S]*?)\n\s*\1\b/.exec(command);
  if (heredoc) return [heredoc[2].trim()];
  const hereString = /@'\r?\n([\s\S]*?)\r?\n'@/.exec(command);
  if (hereString) return [hereString[1].trim()];
  // -m, -am and --message, each with a double-quoted, single-quoted or bare value.
  const flags = [...command.matchAll(/(?:\s-[a-zA-Z]*m|\s--message)(?:\s+|=)(?:"((?:[^"\\]|\\.)*)"|'([^']*)'|([^\s'"]+))/g)];
  if (flags.length > 0) return [flags.map((flag) => flag[1] ?? flag[2] ?? flag[3]).join('\n\n')];
  return null;
}

/** Why a commit message breaks the format, or null when it is fine. */
export function commitMessageProblem(message) {
  if (/co-authored-by:[^\n]*(claude|anthropic|devin|cognition|copilot|cursor)|generated (with|by) (claude|devin|ai\b)|\u{1F916}/iu.test(message)) {
    return 'Commit messages carry no AI attribution: no Co-Authored-By for an agent and no "Generated with" line.';
  }
  const subject = message.split('\n')[0].trim();
  if (!SUBJECT.test(subject) || subject.length > MAX_SUBJECT_CHARS) {
    return `The subject must be "type(scope): summary" in at most ${MAX_SUBJECT_CHARS} characters, with type one of ${COMMIT_TYPES.replaceAll('|', ', ')}. Got: "${subject}". Example: feat(search): rank results by distance`;
  }
  return null;
}

/** Why a command would destroy work or history, or null. */
export function destructiveProblem(command) {
  if (/\bgit\s+push\b[^|;&\n]*(\s--force(-with-lease)?\b|\s-f\b|\s\+\S)/.test(command)) {
    return 'Force pushes rewrite history the user may rely on. Push normally, or ask the user.';
  }
  if (/--no-verify\b/.test(command)) {
    return 'Git hooks keep the repository clean. Fix what they report instead of skipping them.';
  }
  const discards = [
    /\bgit\s+reset\b[^|;&\n]*--hard\b/,
    /\bgit\s+clean\b[^|;&\n]*\s-[a-zA-Z]*f/,
    /\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)/,
    /\bgit\s+stash\s+(drop|clear)\b/,
  ];
  if (discards.some((pattern) => pattern.test(command))) {
    return 'This throws away uncommitted work. Commit or stash it first; to undo one change, restore that file or revert that commit.';
  }
  if (/\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(\/|~|\$HOME|\.\.?|\*|[A-Za-z]:[\\/]?)(\s|$)/.test(command)) {
    return 'That deletes far more than the project. Name the folder to remove.';
  }
  return null;
}

/** The paths a `git add` in this command names, and whether it stages everything. */
function addedPaths(command) {
  const paths = [];
  let stagesAll = false;
  for (const match of command.matchAll(/\bgit\s+add\b([^|;&\n]*)/g)) {
    for (const word of match[1].trim().split(/\s+/).filter(Boolean)) {
      if (['-A', '--all', '.', ':/', '*', ':/*'].includes(word)) stagesAll = true;
      else if (!word.startsWith('-')) paths.push(word.replace(/^["']|["']$/g, '').replace(/\\/g, '/'));
    }
  }
  return { paths, stagesAll };
}

/** Why this command would put a secret into git history, or null. */
export function secretProblem(command, cwd) {
  if (!/\bgit\s+(add|commit)\b/.test(command)) return null;
  const status = git(cwd, ['status', '--porcelain=v1', '-z', '--untracked-files=all']);
  if (status === null) return null;
  const { paths, stagesAll } = addedPaths(command);
  const commitsTracked = /\bgit\s+commit\b[^|;&\n]*\s-[a-zA-Z]*a/.test(command);
  const entries = status.split('\0');
  for (let index = 0; index < entries.length; index += 1) {
    const code = entries[index].slice(0, 2);
    const file = entries[index].slice(3);
    // A rename or copy is followed by its original path, which is not an entry of its own.
    if (/^[RC]/.test(code)) index += 1;
    if (file === '' || !isSecretFile(file)) continue;
    const named = paths.some((p) => p === file || file.startsWith(`${p.replace(/\/$/, '')}/`));
    if (/^[AMR]/.test(code) && /\bgit\s+commit\b/.test(command)) {
      return `${file} is staged and holds secrets. Run git rm --cached ${file}, add it to .gitignore, and commit again.`;
    }
    const stagesIt = stagesAll || named || (commitsTracked && code === ' M');
    if (stagesIt && (code === '??' || code[1] === 'M')) {
      return `${file} holds secrets and is not ignored. Add it to .gitignore (git rm --cached it if it is tracked) before staging; hackathon repositories are usually public.`;
    }
  }
  return null;
}

/** Why a shell command must not run, or null to let it run. */
export function reviewCommand(command, cwd) {
  const destructive = destructiveProblem(command);
  if (destructive !== null) return destructive;
  const secret = secretProblem(command, cwd);
  if (secret !== null) return secret;
  for (const message of commitMessages(command) ?? []) {
    const problem = commitMessageProblem(message);
    if (problem !== null) return problem;
  }
  return null;
}

// File edits: patterns that make a build fake or sloppy.

const UI_FILE = /\.(tsx|jsx|vue|svelte|astro|html|css|scss)$/;
const SOURCE_FILE = /\.(tsx?|jsx?|mjs|cjs|vue|svelte|astro|py|go|rs|html|css|scss)$/;
// Tests, scripts, generated output and library components (shadcn's components/ui) are not checked.
const SKIPPED_FILE = /(^|\/)(\.claude|\.devin|\.work|node_modules|dist|build|\.next|tests?|__tests__|e2e|scripts|components\/ui)\/|\.(test|spec|stories)\.|smoke/;

// Each check: which files, what to look for, and what to tell the agent the first time it appears.
const EDIT_CHECKS = [
  {
    id: 'fake-mode',
    files: SOURCE_FILE,
    // mockData, useMockData, isDemoMode, USE_MOCK_DATA, OFFLINE_MODE and the like.
    pattern: /\b(?:is|use|enable|with)?(?:[Mm]ock|[Ff]ake|[Dd]emo|[Oo]ffline|[Ss]imulated?)(?:Mode|Data|Responses?|Api)\b|\b(?:[A-Z0-9]+_)*(?:MOCK|FAKE|DEMO|OFFLINE|SIMULATED?)_(?:MODE|DATA|API|RESPONSES?)\b/,
    note: 'a mock, demo or offline mode on the product path. The product runs on the real service; when a key is missing it fails with a message naming the variable.',
  },
  {
    id: 'simulated-call',
    files: SOURCE_FILE,
    pattern: /simulat\w*\s+(?:an?\s+|the\s+)?(?:api|network|server|backend|response|latency|delay|loading|request|call)/i,
    note: 'code that pretends to call a service. Call the real one.',
  },
  {
    id: 'placeholder-copy',
    files: UI_FILE,
    pattern: /lorem ipsum|coming soon|\b(?:demo only|for demonstration|not real data|sample data|mock data|this is a demo|simulated data)\b|>\s*(?:Demo|Mock|Beta|Simulated|Sample)\s*</i,
    note: 'placeholder or "demo" copy. Every word on screen is real and specific; nothing is labelled demo, mock, sample or beta.',
  },
  {
    id: 'ai-palette',
    files: UI_FILE,
    pattern: /\b(?:bg|text|from|via|to|border|ring|outline|shadow|fill|stroke|decoration|accent|divide)-(?:violet|purple|indigo|fuchsia)-\d{2,3}\b|#(?:8b5cf6|7c3aed|6d28d9|6366f1|4f46e5|a855f7|9333ea)\b/i,
    note: 'violet, purple, indigo or fuchsia, the generated-UI default. Use the neutral tokens and the single accent from the frontend skill.',
  },
  {
    id: 'gradient',
    files: UI_FILE,
    pattern: /\bbg-(?:gradient|linear|radial|conic)-|\b(?:linear|radial|conic)-gradient\(|bg-clip-text|background-clip:\s*text/,
    note: 'a gradient or gradient text. Flat surfaces, one accent.',
  },
  {
    id: 'decoration',
    files: UI_FILE,
    // Pulse is left out: it is how a loading skeleton says it is loading.
    pattern: /\bblur-(?:2xl|3xl)\b|shadow-\[0_0_\d+px|animate-(?:bounce|ping)\b/,
    note: 'decorative blur, glow or looping animation. Motion and effects only where they tell the user something.',
  },
  {
    id: 'emoji',
    files: UI_FILE,
    pattern: /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u,
    note: 'an emoji in the interface. Use words, or one icon where it carries meaning.',
  },
  {
    id: 'font',
    files: UI_FILE,
    pattern: /\b(?:Inter|Poppins|Roboto|Montserrat|Open_Sans|Lato|Nunito|Space_Grotesk)\b[^\n]*(?:next\/font|font-family)|font-family:[^;\n]*\b(?:Inter|Poppins|Roboto|Montserrat|Open Sans|Lato|Nunito|Space Grotesk)\b/,
    note: 'a typeface other than the kit default. Use Geist, and Geist Mono for numbers and code, unless the spec names a brand font.',
  },
];

/** The files an edit tool call changed: Claude names one, Devin's apply_patch carries a patch. */
export function editedFiles(toolInput) {
  if (typeof toolInput === 'string') {
    return [...toolInput.matchAll(/^\*\*\* (?:Add|Update) File: (.+)$|^\*\*\* Move to: (.+)$/gm)].map((match) => (match[1] ?? match[2]).trim());
  }
  const file = toolInput?.file_path ?? toolInput?.path ?? toolInput?.notebook_path;
  return typeof file === 'string' ? [file] : [];
}

/** The checks one file breaks, each with the first lines it appears on. */
export function editNotes(file, text) {
  const relative = file.replace(/\\/g, '/');
  if (SKIPPED_FILE.test(relative)) return [];
  const lines = text.split(/\r?\n/);
  return EDIT_CHECKS.filter((check) => check.files.test(relative)).flatMap((check) => {
    const hits = lines.flatMap((line, index) => (check.pattern.test(line) ? [index + 1] : [])).slice(0, 3);
    return hits.length > 0 ? [{ id: check.id, lines: hits, note: check.note }] : [];
  });
}

/** Notes for the files an edit changed, each said once per file and check. */
function reviewEdit(root, toolInput) {
  const noted = new Set(readState(root, 'noted.json', []));
  const messages = [];
  for (const file of editedFiles(toolInput)) {
    const absolute = path.isAbsolute(file) ? file : path.join(root, file);
    const relative = path.relative(root, absolute).replace(/\\/g, '/');
    if (relative.startsWith('..') || !fs.existsSync(absolute)) continue;
    for (const hit of editNotes(relative, fs.readFileSync(absolute, 'utf8'))) {
      const key = `${relative}|${hit.id}`;
      if (noted.has(key)) continue;
      noted.add(key);
      messages.push(`- ${relative}:${hit.lines.join(',')}: ${hit.note}`);
    }
  }
  if (messages.length === 0) return null;
  writeState(root, 'noted.json', [...noted]);
  return `Kit check, said once. Fix these, or keep one and say why in your report:\n${messages.join('\n')}`;
}

// The smoke check at the end of a turn.

/** The command that runs the project's smoke check, or null when it has none yet. */
export function smokeCommand(root) {
  const manifest = path.join(root, 'package.json');
  if (fs.existsSync(manifest)) {
    try {
      if (JSON.parse(fs.readFileSync(manifest, 'utf8')).scripts?.smoke) {
        const runner = [['pnpm-lock.yaml', 'pnpm'], ['bun.lock', 'bun'], ['bun.lockb', 'bun'], ['yarn.lock', 'yarn']]
          .find(([lock]) => fs.existsSync(path.join(root, lock)))?.[1] ?? 'npm';
        return `${runner} run smoke`;
      }
    } catch {
      // A package.json that does not parse has no usable smoke script; the build will say why.
    }
  }
  if (fs.existsSync(path.join(root, 'scripts', 'smoke.mjs'))) return 'node scripts/smoke.mjs';
  if (fs.existsSync(path.join(root, 'scripts', 'smoke.py'))) {
    return fs.existsSync(path.join(root, 'uv.lock')) ? 'uv run python scripts/smoke.py' : 'python scripts/smoke.py';
  }
  if (fs.existsSync(path.join(root, 'scripts', 'smoke.sh'))) return 'bash scripts/smoke.sh';
  return null;
}

/** A fingerprint of the code as it stands, or null outside a git repository. */
export function codeState(root) {
  const exclude = ['--', '.', ':(exclude).work'];
  const head = git(root, ['rev-parse', '-q', '--verify', 'HEAD']) ?? 'none';
  const status = git(root, ['status', '--porcelain=v1', '-z', '--untracked-files=all', ...exclude]);
  if (status === null) return null;
  const hash = createHash('sha256').update(head).update(status);
  hash.update(git(root, ['diff', 'HEAD', '--binary', ...exclude]) ?? git(root, ['diff', '--cached', '--binary']) ?? '');
  // Untracked files have no diff, so their content goes in directly, capped for safety.
  const untracked = status.split('\0').filter((entry) => entry.startsWith('??')).map((entry) => entry.slice(3)).slice(0, 2000);
  for (const file of untracked) {
    const stats = fs.statSync(path.join(root, file), { throwIfNoEntry: false });
    if (stats?.isFile() && stats.size < 1024 * 1024) hash.update(file).update(fs.readFileSync(path.join(root, file)));
  }
  return hash.digest('hex');
}

/** True when the repository holds code beyond the kit's own files. */
function hasProductCode(root) {
  const files = git(root, ['ls-files', '--cached', '--others', '--exclude-standard']) ?? '';
  return files.split('\n').some((file) => SOURCE_FILE.test(file) && !/^(\.claude|\.devin|\.work)\//.test(file));
}

/** Runs the smoke command, killing its whole process tree if it runs past the timeout. */
export function runSmoke(command, root, timeoutMs = SMOKE_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const child = spawn(command, { cwd: root, shell: true, detached: process.platform !== 'win32' });
    let output = '';
    let timedOut = false;
    const collect = (chunk) => {
      output = `${output}${chunk}`.slice(-20000);
    };
    child.stdout.on('data', collect);
    child.stderr.on('data', collect);
    const timer = setTimeout(() => {
      timedOut = true;
      if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F']);
      else process.kill(-child.pid, 'SIGKILL');
    }, timeoutMs);
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code: timedOut ? null : code, output, timedOut });
    });
  });
}

/** The last lines of a smoke run, enough to see what failed. */
function tail(output, lineCount = 40) {
  return output.trimEnd().split(/\r?\n/).slice(-lineCount).join('\n');
}

/**
 * Decides whether the agent may end its turn. Returns {block, reason} or {warning} or null:
 *   no product code, or no change since the last result: nothing to do
 *   no smoke command yet: ask for one, once per session
 *   smoke passes, or says it cannot run here (exit 3): the turn ends
 *   smoke fails: keep working, at most twice per state and four times in a row
 */
export async function reviewStop(root, sessionId, run = runSmoke) {
  if (process.env.KIT_SMOKE === 'off') return null;
  const state = codeState(root);
  if (state === null || !hasProductCode(root)) return null;
  const smoke = readState(root, 'smoke.json', { checked: null, stops: {}, inARow: 0, asked: [] });
  const command = smokeCommand(root);
  if (command === null) {
    if (smoke.asked.includes(sessionId)) return null;
    writeState(root, 'smoke.json', { ...smoke, asked: [...smoke.asked, sessionId].slice(-20) });
    return { block: true, reason: 'This project has no smoke check yet. Add one (verify skill: an npm "smoke" script or scripts/smoke.py) that runs every demo flow against the real app, run it, and fix what fails. If this change truly needs none, say why in your reply.' };
  }
  if (smoke.checked === state) return null;
  const result = await run(command, root);
  if (result.code === 0) {
    writeState(root, 'smoke.json', { ...smoke, checked: state, stops: {}, inARow: 0 });
    return null;
  }
  if (result.code === SMOKE_NOT_CONFIGURED) {
    writeState(root, 'smoke.json', { ...smoke, checked: state });
    return { warning: `Smoke check could not run here: ${tail(result.output, 5)}` };
  }
  const stops = (smoke.stops[state] ?? 0) + 1;
  if (stops > MAX_STOPS_PER_STATE || smoke.inARow >= MAX_STOPS_IN_A_ROW) {
    writeState(root, 'smoke.json', { ...smoke, checked: state });
    return { warning: `Smoke check still failing (${command}). Say so in the report.` };
  }
  writeState(root, 'smoke.json', { ...smoke, stops: { [state]: stops }, inARow: smoke.inARow + 1 });
  const what = result.timedOut ? `did not finish in ${SMOKE_TIMEOUT_MS / 1000} s; it must start, check and stop the app on its own` : `exited ${result.code}`;
  return { block: true, reason: `The smoke check (${command}) ${what}. Fix the cause in the product, not the check, then end the turn again. Last lines:\n${tail(result.output)}` };
}

// Entry point.

/** Reads the hook payload from stdin. */
function readPayload() {
  const text = fs.readFileSync(0, 'utf8');
  return text.trim() === '' ? {} : JSON.parse(text);
}

/** Handles one hook call: exit 2 with a reason on stderr blocks, in both agents. */
async function main() {
  const payload = readPayload();
  const root = projectRoot();
  const event = payload.hook_event_name;
  if (event === 'PreToolUse' && SHELL_TOOLS.has(payload.tool_name)) {
    const command = String(payload.tool_input?.command ?? '');
    const problem = reviewCommand(command, payload.tool_input?.workdir ?? root);
    if (problem !== null) {
      process.stderr.write(`Kit: ${problem}\n`);
      process.exitCode = 2;
    }
  } else if (event === 'PostToolUse' && EDIT_TOOLS.has(payload.tool_name)) {
    const context = reviewEdit(root, payload.tool_input);
    if (context !== null) {
      process.stdout.write(`${JSON.stringify({ hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: context } })}\n`);
    }
  } else if (event === 'Stop') {
    const verdict = await reviewStop(root, payload.session_id ?? 'session');
    if (verdict?.block) {
      process.stderr.write(`Kit: ${verdict.reason}\n`);
      process.exitCode = 2;
    } else if (verdict?.warning) {
      process.stdout.write(`${JSON.stringify({ systemMessage: `Kit: ${verdict.warning}` })}\n`);
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    // Fail open: a bug in the kit must never stop the agent's work.
    process.stderr.write(`Kit hook error (ignored): ${error?.stack ?? error}\n`);
    process.exitCode = 0;
  });
}

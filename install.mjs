// Copies the hackathon kit into a project folder without replacing anything that already exists.
//   node install.mjs <project folder> [--dry-run]
// A missing file is copied, an identical one is skipped, and a different one is left alone and
// listed. The project's .gitignore gains the kit's lines that it lacks. Nothing else is touched.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const KIT = path.dirname(fileURLToPath(import.meta.url));
const KIT_FILES = ['AGENTS.md', '.mcp.json', '.claude/settings.json', '.claude/hooks/kit.mjs', '.claude/skills', '.devin/config.json'];
const IGNORED = ['.env', '.env.*', '!.env.example', '.work/', '.claude/settings.local.json', '.devin/config.local.json', 'node_modules/'];

/** Every file under a kit path, relative to the kit folder. */
function filesUnder(relative) {
  const absolute = path.join(KIT, relative);
  if (!fs.statSync(absolute).isDirectory()) return [relative];
  return fs.readdirSync(absolute).flatMap((name) => filesUnder(path.posix.join(relative, name)));
}

/** Copies the kit's files, reporting what was copied, already there, or left alone. */
function copyKit(target, isDryRun) {
  const report = { copied: [], identical: [], different: [] };
  for (const relative of KIT_FILES.flatMap(filesUnder)) {
    const from = path.join(KIT, relative);
    const to = path.join(target, relative);
    if (!fs.existsSync(to)) {
      report.copied.push(relative);
      if (!isDryRun) {
        fs.mkdirSync(path.dirname(to), { recursive: true });
        fs.copyFileSync(from, to, fs.constants.COPYFILE_EXCL);
      }
    } else if (fs.readFileSync(from).equals(fs.readFileSync(to))) {
      report.identical.push(relative);
    } else {
      report.different.push(relative);
    }
  }
  return report;
}

/** Adds the kit's ignore lines that the project's .gitignore lacks; returns the ones added. */
function extendGitignore(target, isDryRun) {
  const file = path.join(target, '.gitignore');
  const current = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
  // `node_modules` and `node_modules/` ignore the same thing, so compare without the slash.
  const bare = (line) => line.trim().replace(/\/$/, '');
  const present = new Set(current.split(/\r?\n/).map(bare));
  const missing = IGNORED.filter((line) => !present.has(bare(line)));
  if (missing.length > 0 && !isDryRun) {
    const separator = current === '' || current.endsWith('\n') ? '' : '\n';
    fs.writeFileSync(file, `${current}${separator}${current === '' ? '' : '\n'}# hackathon kit\n${missing.join('\n')}\n`);
  }
  return missing;
}

/** Things the user should know about the project that the installer will not change itself. */
function notices(target) {
  const found = [];
  const claudeFiles = ['CLAUDE.md', '.claude/CLAUDE.md', 'CLAUDE.local.md'].filter((name) => fs.existsSync(path.join(target, name)));
  for (const name of claudeFiles) {
    if (!fs.readFileSync(path.join(target, name), 'utf8').includes('@AGENTS.md')) {
      found.push(`${name} exists, so Claude Code reads it instead of AGENTS.md. Add a line "@AGENTS.md" to it.`);
    }
  }
  if (!fs.existsSync(path.join(target, '.git'))) found.push('Not a git repository yet: run git init so work lands in commits and the smoke check can tell what changed.');
  return found;
}

const [targetArg, ...flags] = process.argv.slice(2);
if (!targetArg) {
  console.error('Usage: node install.mjs <project folder> [--dry-run]');
  process.exit(1);
}
const target = path.resolve(targetArg);
const isDryRun = flags.includes('--dry-run');
fs.mkdirSync(target, { recursive: true });
const report = copyKit(target, isDryRun);
const ignored = extendGitignore(target, isDryRun);
const lines = [
  `${isDryRun ? 'Would install' : 'Installed'} the hackathon kit into ${target}`,
  `  copied: ${report.copied.length} files`,
  `  already there: ${report.identical.length}`,
  ...report.different.map((file) => `  left alone, differs from the kit: ${file} (merge it by hand)`),
  ignored.length > 0 ? `  .gitignore ${isDryRun ? 'would gain' : 'gained'}: ${ignored.join(' ')}` : '  .gitignore already has the kit lines',
  ...notices(target).map((notice) => `  note: ${notice}`),
];
console.log(lines.join('\n'));

# Hackathon kit for Claude Code and Devin

One set of instructions, skills and hooks that both Claude Code (CLI or desktop app) and Devin (IDE
or CLI) load on their own. It is built for one-shot, unattended builds: the agent ships a product
that works for real, looks clean and can be shown at any moment, without stopping to ask permission
for ordinary work.

## What is in it

```text
AGENTS.md                 the standard, always on in both agents
.claude/skills/           build, frontend, verify, debug, pitch (both agents read them)
.claude/settings.json     the hooks, no AI attribution, Context7 enabled, common commands allowed
.claude/hooks/kit.mjs     the one hook script
.devin/config.json        Devin: read the Claude config, and pre-approve installs and commits
.mcp.json                 Context7, for current library docs (both agents read it)
ONE-SHOT.md               the prompt to paste, and how to start each agent
install.mjs               copies the kit into a project without overwriting anything
tests/                    the hook's tests
```

| Skill | Use |
| --- | --- |
| `build` | The one-shot playbook: plan with an acceptance list, walking skeleton, core job correct, features one at a time, ship |
| `frontend` | Screens that read as a product: one primary flow, Geist, neutral palette, every state, 390 and 1440 px, a screenshot review loop with a measuring script |
| `verify` | The smoke check: starts the real app, runs every demo flow against real services, checks the content, stops the app |
| `debug` | Reproduce, read the real error, fix the cause once, prove it |
| `pitch` | README, demo script and submission text |

## How both agents pick it up

| | Claude Code 2.1.277 or later | Devin (IDE and CLI share one harness) |
| --- | --- | --- |
| `AGENTS.md` | read when the project has no `CLAUDE.md` | read as an always-on rule |
| `.claude/skills/` | native | imported (`read_config_from.claude`, on by default and set in `.devin/config.json`) |
| hooks in `.claude/settings.json` | native | imported; the matchers name both agents' tools (`Bash` and `exec`, `Write` and `apply_patch`) |
| `.mcp.json` | native | imported |

Checked on Devin 3000.10.21: `devin skills list` shows all five skills as user- and model-invoked,
`devin rules list` shows `AGENTS.md` always on, and in a live Smart-mode session the hook refused
`git add -A` with an unignored key file and a malformed commit message, and Devin quoted both
reasons back. In a full unattended build Devin read the skills, wrote the plan with its sources,
and kept to the commit format.

For unattended runs, start Devin in Bypass: Smart mode always asks before `rm` and anything it does
not judge safe, and a question nobody answers stalls the build (`ONE-SHOT.md` has the details).

If a project has its own `CLAUDE.md` (Next.js 16.3 and later write one), it must contain the line
`@AGENTS.md`, which the Next.js one already does.

## Install into a project

```bash
node C:/Users/dchhe/Desktop/skills-hackathon/install.mjs path/to/project
```

It copies what is missing, skips what is identical, lists anything that differs instead of
overwriting it, and adds `.env`, `.work/` and the local config files to `.gitignore`. Add
`--dry-run` to preview. Then put the spec in `SPEC.md`, start the agent as `ONE-SHOT.md` describes,
and paste the prompt.

## What the hooks do

All in `.claude/hooks/kit.mjs`. They stay out of the way of ordinary work: nothing blocks reading,
editing, working on `main` or installing packages.

| When | What happens |
| --- | --- |
| Before a shell command | Refuses: staging or committing `.env` files, keys and credential files that are not ignored; a commit subject that is not `type(scope): summary` within 72 characters; AI attribution in a commit; `--no-verify`; force pushes; `reset --hard`, `clean -f`, `checkout -- .`, `stash drop`; `rm -rf` on `/`, `~`, `.` or `*` |
| After a file edit | Notes once per file the patterns behind fake or sloppy builds: mock, demo or offline modes, simulated calls, placeholder or "demo" copy, violet and indigo, gradients, glows, emoji, a font other than Geist. Tests, scripts and `components/ui` are skipped. Never blocks |
| End of turn | When the code changed since the smoke check last passed, runs it (the npm `smoke` script, or `scripts/smoke.mjs`, `.py` or `.sh`). While it fails the agent keeps working, at most twice per state of the code and four times in a row. Exit 3 from the smoke check means "everything that ran passed, but a key is missing", which warns instead of blocking. A project with code and no smoke check is asked for one, once per session |

The hook fails open: an error inside it never stops the agent. To skip the smoke check for a
session, start the agent with `KIT_SMOKE=off`.

## Why it is built this way

From the Dwelly build (`Desktop/dwelly`), which scored 27 of 30 while simpler entries scored 30:

- The prompt said there were no keys, so the agent built a simulator, mocked ports and replay
  stores. The product was never run for real. Here, no mode fakes the product, and a missing key
  becomes a clear error and a smoke exit 3.
- About 12,000 lines across a nine-stage pipeline, a bakeoff, an ablation tool, a prompt optimiser
  and around 20 versions of an eval harness, while the score barely moved. Here, the design has at
  most five parts, every part must be something a judge sees or the core job needs, and the model
  does the language work rather than hand-coded rules.
- 2,700 lines of skills and rules, a lead and worker subagent hierarchy that deadlocked over who
  owned commits, and duplicated `.claude` and `.devin` copies, with Devin's import of the Claude
  config switched off. Here, there is one copy (`AGENTS.md` and five skills, about 470 lines), no
  subagent hierarchy, and nothing that blocks ordinary work.

## Tried on a real build

One small spec (Fair Weather: a place and an activity in, the best of the next 7 days out, scored
from Open-Meteo, plus a two-sentence OpenAI summary) with the same one-line prompt, no OpenAI key in
the environment, 2026-10-15. One run per column, so this is evidence, not proof.

| | Claude, no kit | Claude, kit | Devin, kit |
| --- | --- | --- | --- |
| Core flow (Lisbon, run) | works | works | blocked: the summary's missing key failed the whole request |
| Misspelled or unknown place | clear message | clear message | clear message |
| Missing OpenAI key | a canned template shown as the summary | the error in the summary's place, scores still shown | the error, but in place of everything |
| Docs checked before coding | none | none | Context7 for 5 sources, plus a live call each |
| Smoke check | none | 5 flows | yes |
| Looked at its own screens | no | yes, 390 and 1440 px | yes, 390 and 1440 px |
| Look | emoji, blue gradient background, coloured scores | Geist, neutral | Geist, warm neutral with one teal accent, decorative circles |
| Commits | 1, free-form message | 1, conventional | 2, conventional |
| Time | 2.4 min | 18.3 min | 28.1 min |

What changed in the kit because of these runs: a failure stays where it happened (a secondary
feature cannot take the core result down), and the smoke check enforces it by running the core
flows without optional keys; every external API and SDK gets a docs check recorded in the plan;
scaffolding no longer moves `node_modules`; decorative background shapes and eyebrow labels joined
the frontend reject list; loading skeletons are no longer flagged; and Devin's config pre-approves
web fetches (`Fetch(https://*)`), which Smart mode otherwise refused.

## Testing the kit

```bash
node --test "tests/*.test.mjs"
```

The tests cover each rule, and the hook end to end with the payloads each agent sends: Claude's
`Bash`, `Write` and `Edit`, and Devin's `exec` with a `workdir` and `apply_patch` with a raw patch.
These shapes were captured from a live Devin session.

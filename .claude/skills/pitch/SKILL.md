---
name: pitch
description: Writes what judges read and watch, namely the README, the demo script, the submission text and the project description, so a judge understands the product in fifteen seconds and can run it. Use when writing or improving any of these, before submitting, and when the product changed what the README shows.
---

# What judges read

A judge gives the README fifteen seconds and the demo two minutes. Every claim must be something
that works right now on the smoke-checked path.

## README, in this order

1. The name, and one line: who it is for and what it does for them.
2. A screenshot of the core result (copy the best one from `.work/screens/` to `docs/`).
3. What it does: three to five bullets, each something a judge can try.
4. How it works: three to six lines, or a small mermaid diagram, of the real flow (screen, API,
   model or service, result). Name each sponsor's technology and the file that uses it.
5. Run it: prerequisites, `cp .env.example .env` with each variable and where to get it, one command
   to start, and `npm run smoke` to check it.
6. Limits and next steps: short and honest.

## Demo script, two minutes

1. The problem, in one sentence a judge has felt.
2. The core flow, live, with realistic input prepared in advance.
3. The result, and why it is right: point at the evidence on screen.
4. One detail that shows depth: a hard case handled, or the sponsor's technology doing real work.
5. The one line again.

Rehearse it against the running app. It follows only smoke-checked paths and never relies on
anything that has not run today.

## Submission text

The one line, three bullets of what it does, the stack, and links to the repository and the video.

## Style

Plain and specific. No "AI-powered", "revolutionary", "seamless" or "cutting-edge", no emoji
headings, no em dashes, and no number that did not come from a real run.

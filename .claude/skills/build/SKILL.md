---
name: build
description: Builds a hackathon product end to end from a spec, brief or one-shot prompt, unattended, in thin working slices that a smoke check proves one by one. Use when asked to build, make, start or ship a product, an MVP or a hackathon project, or to work through a spec until it is done.
argument-hint: "[spec file]"
---

# Build the product

Copy this checklist to the top of `.work/plan.md` and keep it current:

```text
- [ ] 1. Read everything and write the plan
- [ ] 2. Walking skeleton, smoke-checked, committed
- [ ] 3. Core job correct on realistic input
- [ ] 4. Features in the order judges reward
- [ ] 5. Every screen passes the frontend review
- [ ] 6. Ship: README, smoke from a clean start, final commit
```

## 1. Read everything and write the plan

Read the whole spec, every file, link and repository it names, and the docs of every sponsor
product and API it uses (AGENTS.md, Look things up). A summary is not a substitute for the source.
Then write the rest of `.work/plan.md`:

```markdown
# <Product>: <who it is for, and what it does for them, in one line>
Judged on: <live demo, benchmark, code review, sponsor use: from the brief>

## Acceptance: what a judge does, and sees
- [ ] A1 Paste a job post and press Analyse: see the three missing skills, each quoting the post
- [ ] A2 ...

## Stack and shape
<the stack, and at most five parts, e.g.: Next.js page, one route handler, the model call, SQLite>

## Sources checked
- <each external API, SDK and framework: the doc or Context7 query used, and the exact endpoint,
  method or model name it confirmed>

## Decisions
- <what the spec left open, what you chose, and why>

## Out of scope
- <what you will not build>
```

- Four to ten acceptance items, each a judge's action and what they then see, with concrete values
  from the spec. They define done, and each becomes a flow in the smoke check.
- More than five parts means the design is too big: cut until it fits, unless the spec names them.
- When the spec is silent on something a judge will notice, decide and record it under Decisions.
- Before the first commit, `.gitignore` holds `.work/`, `.env`, `.env.*` and `!.env.example`.

## 2. Walking skeleton (the first hour at most)

Real input to real output through the real stack: the screen calls the API, the API calls the real
service or model, and the result renders. Rough is fine; fake is not.

- Scaffold with the framework's own generator (`npx create-next-app@latest`, `npx shadcn@latest
  init`, `uv init`). Generators refuse a folder that already has files, so generate into a sibling
  folder without installing (`create-next-app ../app-gen --skip-install ...`), move the files up,
  then install in place. Moving `node_modules` breaks it. Keep the kit's `AGENTS.md`: a block the
  generator writes into `AGENTS.md` or `CLAUDE.md` stays, below the kit's text.
- Write the smoke check for A1 now (verify skill), run it until it passes, and commit.
- A key is missing: build the call anyway from the provider's docs, make the smoke check exit 3
  naming the variable, and note it in the plan. Never stub the call.

## 3. Make the core job correct

The part judges test gets the depth. Run it on the spec's own examples and on realistic messy
input: empty, very long, the wrong format, the ambiguous case the spec mentions. Keep those
examples as tests with literal expected values. Fix by cause, never by special-casing an example.
For a model call: structured output, a system prompt that states the spec's rules, validation of
the result, and one retry on a malformed answer.

## 4. Features, in the order judges reward

For each acceptance item in turn: build it, handle its errors (AGENTS.md, Reliable), add its flow
to the smoke check, run the smoke check, tick it in the plan, and commit. Finish one before starting
the next. If one still fails after two honest attempts, cut it from the UI, record why, and move on.

## 5. Screens

Every screen a judge sees goes through the frontend skill, including its screenshot review.

## 6. Ship

- Write the README with the pitch skill. `.env.example` lists every variable.
- Stop every dev server, run the smoke check from a clean start, and commit.
- Report as AGENTS.md says under When you finish.

## When a score decides

When the event scores a benchmark or test set: get the scorer running first and record a trivial
baseline. Then change one thing per run and keep it only when the score moves beyond run-to-run
noise. Read every failure. Never tune on the held-out split and never special-case test inputs.
Report the real number and where it came from.

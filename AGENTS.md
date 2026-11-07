# How to build here

This is a hackathon project. The goal is a product that does its core job for real, looks clean,
and can be shown to judges at any moment, shipped fast. These rules apply to every agent in every
session and after every context reset. The skills hold the detail: when the table says so, read
`.claude/skills/<name>/SKILL.md` before starting, even if your agent did not load it for you.

| Doing this | Read first |
| --- | --- |
| Building the product from a spec, a brief or a one-shot prompt | `build` |
| Any screen, component, layout, style or UI copy | `frontend` |
| Writing the smoke check, or proving a feature works | `verify` |
| Anything broken, failing, erroring or wrong | `debug` |
| The README, the demo script or the submission text | `pitch` |

## What wins

In this order: it works for real, end to end; the core job is done correctly on realistic input;
it is obvious to use and looks clean; a stranger can read the code; everything else. Depth goes
where judges look (the core flow and its result). Everything else stays thin.

## Real, never simulated

- No mock, demo, offline or "simulated" mode, no fake latency, no fallback that returns canned data
  when a call fails, and no switch that fakes the product. There will be internet.
- A missing API key never stops the build and never causes a fake. Build the real integration from
  the provider's docs, read the key from the environment, and fail on first use with a message that
  names the variable. List every variable in `.env.example`.
- Seed data that makes the first screen look alive is fine when real input works the same way.
- Tests may replay recorded responses. The product never does.
- No "demo", "mock", "sample", "beta" or "coming soon" labels, and no control that does nothing.
  Cut an unfinished feature from the UI rather than show it.

## Right-sized

The smallest design that does the job well.

- Use the spec's stack. With none: Next.js (App Router) with TypeScript, Tailwind and shadcn/ui,
  with route handlers as the backend. Add a database only when data must outlive a request (SQLite
  first). Use Python (FastAPI) only when the core needs Python libraries.
- One app and one process where possible. No microservices, queues, plugin systems, registries,
  custom frameworks, config layers, feature flags or eval harnesses unless the spec asks for them.
- Let the model do language work: classify, extract, rank, summarise, write. Code does arithmetic,
  I/O, validation and anything that must be exact. Never hand-code language rules that a model call
  would handle better.
- No abstraction, option or file with a single use. A mature library beats your own code; the
  standard library beats a new dependency for small jobs.
- Before adding any part, ask: will a judge see it, or will the core job break without it? If
  neither, leave it out.

## Look things up

Your memory of an API can be a version behind, and a wrong guess costs more than a lookup. Before
writing the code for each of these, check the current docs, and note the source in the plan:

- every external API or SDK the product calls (model providers, data APIs, payments, auth);
- the sponsor's product, whose docs you read before designing anything around it;
- the framework and UI library setup at the installed major version (from the lockfile).

How, in order:

1. Context7: `resolve-library-id`, then `query-docs` with one specific question (the endpoint, the
   method, the model name, the request and response shape).
2. If Context7 is unavailable or lacks it, the official docs page.
3. Then a web search for current practice; read the best two or three results, not one.

Then call the real API once (with `curl` or a three-line script) and look at the actual response
before writing code against it. Skip lookups for the language itself and for code that touches no
outside interface.

## Reliable, in proportion

At every boundary with the outside world (HTTP APIs, model calls, files, user input):

- Set a timeout, check the status, and read the error body.
- 401 or 403: say the key is wrong or missing. 429 and 5xx: retry twice with backoff, then fail
  clearly. Anything else: fail clearly.
- Validate what comes back before using it (zod in TypeScript, pydantic in Python). For model
  output, ask for structured output (a JSON schema or a tool call), validate it, retry once.
- Show the user a plain error and a way to retry. Never swallow an error, never show a success that
  did not happen, never leave a spinner running forever.
- Keep a failure where it happened. When a secondary part (a summary, a suggestion, an enrichment)
  fails or lacks its key, the core result still shows, and the error appears in that part's place.
  Fetch secondary parts separately so they cannot take the core result down with them.
- Stream long model output. Anything slower than a second shows progress.

Nothing more without a measured need: no circuit breakers, caches, queues or retry frameworks.

## Prove it works

- The project has a smoke check: an npm `smoke` script, or `scripts/smoke.mjs`, `scripts/smoke.py`
  or `scripts/smoke.sh`. It starts the real app, runs every demo flow against it with real services,
  checks what comes back, and stops the app, in under two minutes. The verify skill shows how.
- Run it after each feature. The end-of-turn hook also runs it when the code changed and keeps you
  working while it fails. Fix the product, never the check.
- Test the logic where a wrong answer would lose: parsers, scoring, money, dates. Use literal
  expected values from the spec. Skip tests nobody needs.
- Before calling a screen done, open it in a browser, take a screenshot and look at it.
- Report only what you ran, and say what you did not verify.

## Code a stranger can follow

- The framework's standard layout, grouped by feature. No `utils`, `helpers`, `common` or `misc`.
- Names say what a thing is or does; booleans read as questions; numbers carry their unit.
- Functions do one thing, about 40 lines at most. Entry points (routes, pages, commands) call the
  logic; SDK and database calls sit at the edges.
- Every module and exported function gets a one-line comment saying what it is for. A line a
  newcomer would stop at (a regex, a magic number, a workaround) gets a short comment. A function
  with several steps names them in two to five lines. No comments that repeat the code, no banners,
  no commented-out code, no TODOs in shipped paths.
- Delete dead code and unused files as you go.

## Working rhythm

- Keep one plan at `.work/plan.md` (git-ignored): the acceptance list, decisions and status. Update
  it after each feature. After a context reset, read it and `git log` before doing anything else.
- Do not hand work back. Ask the user only for keys and for decisions no experiment can settle. For
  everything else, decide, write the decision in the plan, and continue.
- Two failed attempts at the same fix mean a wrong premise. Re-read the error and the docs before a
  third.
- Commit each working step as `type(scope): summary`, at most 72 characters, with no AI
  attribution, and never with `--no-verify`. Keep `.env` and keys out of git. Never force push.
  Push or deploy only when asked.
- When the user gives a deadline: from one hour before it, no new features. Only the demo path,
  fixes, the README and a final commit.

## When you finish

Run the smoke check from a clean start. Then report in a few lines: what works (with the smoke
output), what does not, the environment variables to set, and what you decided on the user's behalf.

---
name: verify
description: Proves the product works the way a judge will use it, through a smoke check that starts the real app, runs every demo flow against real services, checks the content that comes back and stops the app. Use when adding the smoke check, after each feature, when the end-of-turn hook reports a failing smoke check, and before calling anything done.
---

# Prove it works

Green unit tests and a page that renders prove little. The smoke check proves that what a judge
will do works, end to end, right now. The end-of-turn hook runs it whenever the code changed, so a
broken demo path cannot slip through.

## The smoke check

Copy [smoke.template.mjs](smoke.template.mjs) to `scripts/smoke.mjs` and add
`"smoke": "node scripts/smoke.mjs"` to `package.json`. It works for any stack, since `START` can
launch a Python or Go server just as well. Edit four values (`PORT`, `START`, `READY_PATH`,
`REQUIRED_ENV`) and the `FLOWS` list. Without a `package.json`, the hook runs `scripts/smoke.mjs`,
`scripts/smoke.py` or `scripts/smoke.sh` directly.

Its contract, which the hook relies on:

- Exit 0 when every flow works and 1 when one fails. Exit 3 means everything that could run passed
  but a key is missing, so some flows did not run (it prints which). Never use 3 to dodge a real
  failure.
- `REQUIRED_ENV` holds only the keys the core flow cannot work without. A key that one feature needs
  goes in that flow's `needs`, so the core flows still run without it. That proves a missing key or
  a failing secondary service cannot take the core result down.
- It starts the app itself on its own port, waits until it answers, and stops it, along with
  everything it spawned, even when a flow fails.
- It finishes in under two minutes. Use the dev server or a typecheck rather than a full
  production build when the build is slow.

## Writing flows that prove something

- One flow per acceptance item in `.work/plan.md`, named after it (`A1 ...`).
- Call the app the way the screen does (the same route and the same body), with realistic input
  from the spec, against the real model or API.
- Check the content the spec promises: the field is there, it holds the right kind of value, and it
  includes what the input implies (the template checks that GraphQL, named in the posting, comes
  back). A bare 200, or "the response exists", proves nothing.
- Model output varies: check its shape and the facts it must contain, not its exact wording.
- Include the failure case a judge might try (empty input, an unknown city) and check for the clear
  error message.
- When the product is the interface itself, add one browser flow for the main path with Playwright
  (`npm i -D playwright`): open the page, fill the input, press the button, and wait for the result
  text. API flows cover the rest.

## When it fails

Read the output: the flow, the status and the body. Fix the cause in the product (debug skill).
Never loosen a check, skip a flow or return 3 to get green. If a flow keeps failing after two
honest attempts, cut the feature from the UI and from the plan's acceptance list, and say so.

## Before you say done

1. Stop every dev server you started.
2. Run the smoke check from a clean start and read every line.
3. For each screen: open it, take screenshots at 390 and 1440 px (frontend skill), and look at them.
4. Report what passed, quoting the smoke output, and what you did not verify.

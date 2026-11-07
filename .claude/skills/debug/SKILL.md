---
name: debug
description: Finds and fixes the cause of a bug, crash, failing smoke check, failing test, wrong output or flaky behaviour, once, with proof that it is fixed. Use when something is broken, failing, erroring, slow, flaky or giving a wrong answer.
---

# Fix the cause, once

1. **Reproduce it.** Run the failing command, flow or request and capture the exact output. If it
   does not reproduce, add logging at the boundary (request, response, model output) and run again.
2. **Read the actual error**, top to bottom: the first error, its file and line, and the full
   request and response body. Most hackathon bugs are visible in the body that nobody printed.
3. **Find the cause.** Form one hypothesis and test it with the cheapest experiment: a print, a
   `curl`, a three-line script. When a library surprises you, read its docs at the installed
   version (AGENTS.md, Look things up) before guessing.
4. **Fix the cause, not the symptom.** No try/catch that hides it, no special case for this input,
   no retry around a bug, no fallback value.
5. **Prove it.** Rerun the reproduction and the smoke check. If it could come back, add the case to
   the smoke check or a test.

Two failed fixes mean a wrong premise. Write down what you believe about the problem and check each
belief against the source, the docs or a direct experiment before trying again.

Usual causes in a hackathon build, worth checking first:

- The environment: a wrong variable name, `.env` not loaded by this process, or a key for another
  project.
- An SDK or API that changed since your training: model names, method names, response shapes.
- A response shape that differs from what the code assumes: log it and compare.
- A stale process: an old dev server still holding the port, or a cached build.
- The browser side: CORS, a wrong base URL, a hydration mismatch, a server-only module imported into
  a client component.

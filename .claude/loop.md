# Loop

Every iteration:

1. Orient from disk, not memory: git status, current branch, docs/PLAN.md, docs/STATUS.md. After any compaction, re-read CLAUDE.md and this file.
2. If docs/PLAN.md doesn't exist, write it: every SPEC phase as checkbox tasks of 30 to 90 minutes, each naming its module and how it's checked, demo path first within each phase. Human-only checks (VoiceOver walkthrough, Meet tab, Zoom window, rehearsals) go in a Morning section, not the task list.
3. Take the next unchecked task. Read its SPEC section and the docs or types of every API it touches.
4. Build the smallest complete slice, tests first for pure logic.
5. Run `pnpm verify`, plus the related e2e test when its keys work. Fix until green. Send long output to a file in .tmp/ and read the failures, not the whole log.
6. Commit and tick the task.
7. Stuck after three real attempts or about 45 minutes: write in docs/STATUS.md what you tried, the exact error and your next idea, mark the task [blocked], and take the next task that doesn't depend on it.
8. Phase gate, once every task in the phase is checked or blocked: `pnpm doctor`, `pnpm verify`, `pnpm test:e2e` and SPEC's exit criteria. Then a fresh subagent reviews the phase diff against SPEC.md and CLAUDE.md; fix what it finds, merge, tag, start the next phase.
9. After the Phase 4 gate, write the handoff and stop.

# Done

- Every PLAN.md task is checked or [blocked] with a reason. Nothing in SPEC is silently missing.
- On main: `pnpm verify` exits 0; `pnpm test:e2e` passes or skips with the missing key named; axe reports no violations; a fresh clone in .tmp/ installs and verifies; every dependency licence is permissive.
- docs/STATUS.md opens with a handoff that fits on one screen: what works, what's blocked and why, which keys were missing, the exact commands to run the demo and the practice talk, the human checks left, and the risks for the demo.
- Print the final gate output and the handoff in this conversation, then stop.

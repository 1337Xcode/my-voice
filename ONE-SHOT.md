# One-shot prompt

Fill in the brackets, put your spec in `SPEC.md` at the project root, and paste the block into
Claude Code or Devin. Keep the spec to what the product must do and what the judges reward; the
kit already covers how to build.

```text
Build [product name] from SPEC.md for [event], judged on [live demo / benchmark / code review / use
of sponsor X]. The deadline is [time]; I am not available until then.

Follow AGENTS.md and run the build skill from step 1. Keys are in .env (names in .env.example);
[if one is missing, build the real integration anyway, make the smoke check say which variable is
missing, and carry on]. The product talks to the real services: no mock, demo or offline mode.

Make the decisions the spec leaves open, record them in .work/plan.md, and keep going. Work until
every acceptance item passes the smoke check and every screen passes the frontend review. Then
write the README with the pitch skill, commit, and report what works, what does not, and what I
need to set.
```

## Starting the agent so it does not stop to ask

- **Claude Code (CLI):** `claude --permission-mode auto`. Auto mode is the default starting mode in
  recent versions; a classifier approves safe actions and blocks risky ones (force pushes,
  `reset --hard`, piped installs, deploys).
- **Claude Code (desktop app):** choose Auto in the mode selector before sending the prompt.
- **Devin (IDE or CLI), unattended:** Bypass (`/bypass` in the session, or `devin
  --permission-mode dangerous`). Smart mode always asks before any `rm` and anything it does not
  judge safe, and an unanswered question stalls a run while you are away; in a non-interactive run
  it is refused outright, which ends the build. In Bypass, the kit's hook is the safety net: it
  still refuses force pushes, `reset --hard`, broad `rm -rf` and committing secrets.
- **Devin, while you are at the keyboard:** Smart (`/smart`). The kit's `.devin/config.json`
  pre-approves package installs, git commits, web fetches and Context7, which Smart would otherwise
  ask about.

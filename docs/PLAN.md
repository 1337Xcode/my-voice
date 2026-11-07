# Plan: My Voice — a personal speech translator for one person whose speech stock recognisers can't follow

Source of truth: `docs/SPEC.md`. Decisions the spec left open: `docs/DECISIONS.md`. How to run: `docs/RUNBOOK.md`.
Status and handoff: `docs/STATUS.md`. Improvements beyond the spec: `docs/IMPROVEMENTS.md`.

Each phase ends deployed to Modal, running in the Expo development build, with its checks passing.
Modules for later phases may be built ahead in parallel worktrees; they are accepted only at their phase gate.

## Phase 0: Skeleton
- [x] Repo layout (`app/`, `server/`, `server/assets/`, `docs/`, `.env.example`) — checked by `npm run verify`
- [x] Modal app: GPU class, `max_containers=1`, concurrent inputs, 15 min scaledown, `KEEP_WARM`, both volumes, secret — `npm run deploy`
- [x] `/health`, `/wake`, `/ws` hello → ready; `/state`, `/phrases` — `server/tests/test_web_skeleton.py`, smoke P0 flows
- [x] Expo SDK 58 app: four tabs, Settings with hidden developer panel, connection badge — typecheck + web screenshot
- [x] Ready within 60 s cold (measured 4.1 s) and 2 s warm (measured 0.21 to 0.56 s) — `scripts/handshake.mjs`
- [ ] Running on the iPhone (EAS development build) — waiting on Expo login + Apple developer account (RUNBOOK)

## Phase 1: Core loop
- [ ] Server: Silero VAD endpointing (Done tap, silence 500 to 2000 ms, 250 ms minimum speech, 30 s cap)
- [ ] Server: Whisper large-v3-turbo n-best (beam 5, 5 best, length-normalised log-prob), hallucination guards
- [ ] Server: stand-in decision returns `pick` with top 3; `choose` speaks the chosen text
- [ ] Server: ElevenLabs Flash v2.5 TTS, cache by (voice, format, text), phrase pre-synthesis, `/tts/{file}`
- [ ] Server: turn records with every stage timestamp in `turns.jsonl`; `client_timing`
- [ ] App: design system (Geist, lucide, Moti), Talk states Idle/Listening/Thinking/Pick one/Speaking/Ignored/Offline
- [ ] App: capture 16 kHz PCM via @siteed/audio-studio, 100 ms frames over the WebSocket, live level, half duplex
- [ ] App: phrase one-tap online and offline from cached audio (< 0.3 s), typed text via expo-speech offline
- [ ] Check: P1 speaks a sentence → up to 3 options → tapped one is spoken; timings logged; offline phrase < 0.3 s

## Phase 2: Personalise
- [ ] `/clips` upload, conversion to 16 kHz wav, clip records (team CSV columns + ours)
- [ ] Onboarding (consent, voice, phrases, test sentences ta01-ta10, phrase recordings, make my model)
- [ ] Phrase matcher: WavLM-base-plus layer features, banded DTW, leave-one-out layer choice, reject threshold
- [ ] Babble bank (LibriSpeech dev-clean), Harvard lists in `_shared/prompts/`
- [ ] Trainer: LoRA r32/α64 on q/k/v/out, augmentation, early stopping, eval per condition, promote rule, hot swap
- [ ] `import_team` (reads `speech-data/<SPK>/clips.csv` + team audio), `register_adapter` (e.g. `p1-test`)
- [ ] Check: P1 phrase leave-one-out accuracy reported; v1 trains, evaluates, promoted or rejected; app updates live

## Phase 3: Gate and learning
- [ ] Candidate set, Decisions round 1 (Jev via TypeSafe AI; gpt-6-luna option), Haiku repair in parallel, round 2
- [ ] Actions speak/pick/again, Check-first mode, correction memory, Learned note, Review list
- [ ] Check: misheard sentence → Pick → he picks → saying it again yields it via memory; Review approval makes clips trainable

## Phase 4: Results
- [ ] `eval_asr`, `eval_pipeline`, synthetic babble tests, listener/Akoli imports, gate calibration, Results screen
- [ ] Check: Results shows stock vs model vs listeners, latency medians, calibrated threshold, from real data

## Phase 5: Toolkit
- [ ] Read/write profile, SSE events, Tell the app → settings_proposal → confirm
- [ ] Check: text size syncs both ways within 5 s; "bigger text" spoken by P1 gives a confirm card

## Phase 6: Calls
- [ ] Twilio call, `<Connect><Stream>`, callee captions, his sentences as ulaw_8000, pulse tone, opening line
- [ ] Check: a call to a verified phone works end to end

## Phase 7: Hands-free
- [ ] ECAPA speaker gate, hands-free toggle, partner captions, Them button, partials
- [ ] Check: the other person's speech becomes captions and is never spoken

## Morning (human checks)
- [ ] Install the development build on the iPhone (RUNBOOK) and repeat each phase check on the device
- [ ] VoiceOver walkthrough of Talk, Pick one and Speaking
- [ ] A Twilio test call to a teammate's verified phone

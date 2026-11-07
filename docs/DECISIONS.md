# Decisions

Every choice the build made that the spec didn't fix, and every place it differs from the spec, with why.
Sources for API facts are in `docs/API-NOTES.md`.

## Repository and process

- **`docs/TEAM.md` was not in the repo.** The team contract was read from the team's real data on the volumes instead:
  `speech-data/P1/clips.csv` (columns `id,speaker,text,file,split,condition,ok,notes`, ids like `P1_r001`, `P1_t01`,
  `ok` as `yes`/`no`, `file` like `practice/P1_r001.m4a`), audio in `speech-data/P1/incoming/` (m4a) and `speech-data/P1/wav/`,
  and a LoRA adapter at `speech-models/p1-test/` (rank 32, alpha 64, q/k/v/out projections, with `train_config.json`).
  The import and `register_adapter` read these directly. `SPEC.md` moved to `docs/SPEC.md` as section 5 lays out.
- **Plan files.** `.claude/loop.md` asks for `docs/PLAN.md` and `docs/STATUS.md`; AGENTS.md asks for `.work/plan.md`.
  The plan lives in `docs/PLAN.md` (committed, so teammates see it); `.work/` holds only scratch state.
- **npm, not pnpm.** Expo with pnpm needs hoisting configuration; npm is the Expo default. `pnpm verify` still runs the same scripts.
- **Smoke check targets the deployed server.** The server needs a GPU on Modal, so `npm run smoke` checks the deployed app
  (`npm run deploy` first); `npm run verify` adds the app typecheck and the server's pytest suite.

## Environment

- **Env names follow the user's `.env`.** `ELEVENLABS_VOICE_ID` is read as the spec's `ELEVENLABS_DEFAULT_VOICE_ID` (either works).
  `OPENAI_BASE_URL` (EU endpoint), `DECIDE_MODEL=jev-latest`, `PARSE_MODEL=gpt-6-luna` and `TYPESAFE_API_KEY` are honoured.
  `INTERNAL_TOKEN` was added for the trainer → `/internal/reload` call. `APP_TOKEN` and `INTERNAL_TOKEN` were generated.
- **One Modal secret, synced on deploy.** `npm run deploy` writes the non-empty `.env` values into the secret `my-voice-env`,
  so an unset key reads as missing on the server and fails on first use with its name.
- **AssemblyAI key is not used in the product.** Spec 16 says his audio goes only to our Modal volumes and his phone.

## Server

- **GPU A10G for serving** (spec allows A10G or L4): about twice L4's memory bandwidth, which is what decoding latency depends on.
  Modal's docs name it `A10`; `A10G` deploys and is accepted.
- **Session timeout one hour.** A WebSocket is one Modal input; the app reconnects with backoff after the timeout.
- **Region: Modal's default (us-east).** Warm hello→ready from the UK measured 0.21 to 0.56 s. Revisit if turn latency needs it.
- **CORS open to any origin.** Every route needs the bearer token; the web build of the app needs CORS to reach the server.

## App

- **Expo SDK 58** (latest stable, React Native 0.88.1), Expo Router tabs template, npm.
- **iPhone builds go through EAS** because the developer machine is Windows. Dev builds load JS from Metro on the developer
  machine, so `app/.env` (written by `npm run deploy`) supplies the server URL and token without baking them into the binary.
- **Icons:** lucide-react-native for interface icons. `@thesvg/react` renders DOM `<svg>` elements, which don't exist in
  React Native, so it is not used in the native app (it is a brand-logo set; the app shows no brand logos).
- **Motion:** Moti (Framer-Motion-style API on Reanimated, which Expo ships). Framer Motion itself targets the DOM.
- **Look:** follows the user's reference screens: warm cream background, one deep red accent, big round Stop button,
  listener-facing Speaking card, numbered pick cards, pinned patience phrase. Four tabs kept, as the spec requires.
- **Text size:** our scale multiplies the system font scale (React Native's default), so the larger of the two always wins.

## Recogniser and turn pipeline

- **Beam size 5 (spec), with beam agreement passed to the gate.** Beams often differ only in case or punctuation; they are
  merged after normalisation and the count of beams behind each sentence goes to the gate as evidence ("5 of 5 beams,
  word confidence 99.5%"). 8 beams were tried for more distinct hypotheses: ~800 ms vs ~530 ms on the A10G, so 5 stays.
- **Encoder reuse for the no-speech check is not possible through Whisper's `generate`** (it needs `input_features`;
  passing `encoder_outputs` crashes or double-expands beams in transformers 5.22). The no-speech check runs its own
  encoder pass: 56 to 73 ms measured.
- **Speculative recognition.** When he pauses 300 ms, recognisers start on the audio so far; if no speech follows, that
  result is used at the end of the turn. Saves up to the 600 ms between the pause and the 900 ms endpoint.
- **Speaker gate uses WavLM base+ SV x-vectors, not SpeechBrain ECAPA.** SpeechBrain needs `torchaudio`, whose latest
  release (2.11) is pinned to an older torch than the serving image's 2.15. Same rule as the spec: his centroid from
  10+ clips, threshold at the 1st percentile of his own leave-one-out scores.
- **"Tell the app" uses Jev, not Haiku.** Mapping a request onto a fixed list of allowed changes is a calibrated
  choice with "none of these"; Jev can't invent a setting. Live: "make the text bigger" → text size bigger (p 1.0),
  "can I have a flat white please" → no change (p 1.0). The Anthropic key in `.env` is also being rejected (401).
- **Decision gate default is Jev via TypeSafe AI** (`https://api.typesafe.ai/v1/systemone`), per the user. gpt-6-luna
  stays selectable (`decide_provider`); the EU OpenAI endpoint refuses this project (401 geography restrictions, and a
  503 "Decision inference is unavailable" during one run).
- **Live third-party tests are opt-in** (`uv run pytest -m live`) so an outage at a provider can't fail the build check.
- **Old container stopped on deploy.** With `max_containers=1`, an open WebSocket kept the previous version's
  container alive and blocked the new one for minutes; `npm run deploy` now stops it and apps reconnect.

## Calls

- **App-to-app calls by code**, beyond the spec's Twilio calls: his app has a 6-digit call code and a share link
  (`/c/<code>`); a family member opens it in any browser (iPhone Safari included), taps Call, and his app rings. They
  hear only the clear voice and see each sentence large; he sees their words as captions. Works with no Twilio keys.
  Twilio phone calls (spec 13) are built too and switch on when the keys are set.

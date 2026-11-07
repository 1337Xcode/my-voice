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

## Experiments (EXP-SPEC: lips and realtime voice)

- **A separate Experiments area, all off by default.** The server flags `REALTIME_VOICE` and `LIPS` only make an
  experiment available; he switches each on in Settings → Experiments (stored apart from the core settings under
  `experiments.v1`). With a flag off the server sends nothing new and the app shows no new control; with a flag on
  but the switch off, every turn runs exactly the core path. The spec's Talk-screen Lips toggle became its own
  "Talk with lips" screen inside Experiments, so the core Talk screen never changes.
- **The spec's `EXP-SPEC.md` is at the repo root**, not in `docs/`.
- **Flags pass through the shell at deploy time** (`REALTIME_VOICE=1 LIPS=1 npm run deploy`) as well as from `.env`,
  because a deploy from a `.env` without them switches the experiments off.
- **R1 uses ElevenLabs `/multi-stream-input`, not `/stream-input`.** Probed live: `/stream-input` never marks the end
  of a flushed sentence (`isFinal` only arrives when the socket closes), so the app could not know when the voice had
  finished and the microphone could resume. The multi-context endpoint, with one context per sentence and
  `close_context` straight after the flushed text, returns `isFinal` per sentence on one long-lived connection: first
  audio 108–126 ms, end marked every time (5 sentences, pcm_24000 and ulaw_8000). Model `eleven_flash_v2_5`,
  `auto_mode=true`, `inactivity_timeout=180`, an empty-text keepalive every 60 s, speed set per context.
- **R1 sends audio to the app as 24 kHz 16-bit PCM in quarter-second pieces.** ElevenLabs returns about a second of
  audio per chunk; splitting it cut result-to-first-piece from 276–287 ms to 225–246 ms on a UK connection.
- **R1 caches streamed sentences** like the whole-clip voice does (`tts/<voice>/pcm_24000/<hash>.pcm`): a sentence he
  has said before starts 88–98 ms after the result.
- **R1 on web builds only, through Web Audio.** `react-native-audio-api` (spec 6) needs a native build, and none can
  be made yet (no EAS login, Windows machine). The phone runs the web build, so streamed chunks play through one
  `AudioContext`, scheduled back to back; the first tap after switching it on unlocks sound on iOS Safari. If a
  sentence's stream fails before any sound, the whole-clip voice says it instead (real audio, not a stand-in).
- **R1 on calls:** a per-call stream in the far side's format: `ulaw_8000` media messages to Twilio (not testable
  until the Twilio keys are set) and PCM pieces to a guest's browser on app-to-app calls (tested).
- **X0 capture runs in the browser, not in a Swift module or VisionCamera.** Both need a native iOS build, and none can
  be made here (Windows, EAS not logged in), so neither could be spiked. The iPhone runs the web build, so capture uses
  getUserMedia (front camera, 640x480) and MediaPipe Face Landmarker (tasks-vision 1.2.2, GPU with CPU fallback,
  `numFaces: 1` so MediaPipe smooths landmarks). It works the same on iPhone Safari, Android and desktop browsers.
  The library and model load from their pinned CDN files only when a lips screen opens, so the core app's bundle and
  load time don't change. Landmarks run on the main thread (MediaPipe's own pattern); the 10-minute camera test
  measures the cost on the phone.
- **The camera's picture is never shown** (user). The camera plays into a 2 px, near-transparent video element (iOS
  only decodes frames for an attached, playing video). "Set up the camera" draws an outline of the face box and mouth
  from landmarks instead of a preview.
- **TrueDepth and LiDAR are not available to web pages** on iOS Safari (no WebXR depth; the depth-stream draft was
  discontinued), so lips use the normal front camera only.
- **The four alignment points come from the phone.** The lip models align mouths from four face points (eyes, nose
  tip, mouth centre); the browser computes them from the face mesh and sends them in each frame's header, so the
  server needs no MediaPipe (whose Python package no longer has the API the model code uses with numpy 2).
- **The face crop is roll-corrected, eyes 50 px apart, mid-eye 50 px from the top of the 160 px crop**, so the
  models' 96 px mouth patch stays inside the crop. JPEG quality 0.9, grey (R=G=B).
- **The audio clock uses sample counts on both sides.** The app counts samples sent on each connection, the server
  counts samples received; `audio_clock` reports pair a count with the device time, and the median fit maps any turn
  sample to device time. The binary audio frames are unchanged.
- **The sync check is a 10-second `lips_sync` turn** whose silence endpoint is held off; the offset is the lag that
  best lines up the audio energy with the mouth opening (±500 ms, correlation ≥ 0.3, 3+ bursts), stored per device
  (a hash of the browser's user agent) in `<speaker>/lips.json`.
- **"24 fps for 10 minutes" is checked as**: at least 600 s, at least 99% of whole seconds at 24 or more, no camera
  stall (a gap over 200 ms), no microphone gap outside voice playback, and the microphone delivering 16 kHz within 2%.
- **Deploys go from a clean worktree of HEAD** when another session has uncommitted server changes: a deploy of the
  shared working tree once shipped unfinished code and stopped the server until it was redeployed from HEAD.
- **A Lips button on Talk** (user request) appears only when the server runs with `LIPS=1`; it opens the separate
  lips screen. With the flag off, Talk is unchanged.

## Parked: CTranslate2 decoder (not live)

Built (`server/voice/asr/ct2.py`, patch for serving in `.work/ct2-serving.patch`) and measured: 140 ms per clip
instead of ~700 ms, and real n-best (transformers 5.22 returns the same hypothesis five times for Whisper n-best).
With it, S1 v1 scored the same on noisy and babble conditions but 2.5 points lower in quiet (76.5% vs 79.0%), and the
first serving deploy with it failed to start. Kept out of the live app for the demo. Next: build a jobs-only image with
it, replay S1's test set through the whole pipeline (`eval_pipeline`), switch only if the right sentence reaches him at
least as often with no more wrong sentences spoken, and find the start-up failure before any serving deploy.
The jobs score with the serving decoder (transformers), so promotions match what he hears.

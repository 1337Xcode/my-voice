# Runbook

## Waiting on keys or accounts

| What | Needed for | Status |
| --- | --- | --- |
| Expo account (`npx eas-cli login`) and an Apple Developer account | The iPhone development build | Waiting: not logged in |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | Calls (phase 6) | Waiting: empty in `.env` |
| `TOOLKIT_URL`, `TOOLKIT_TOKEN` | Toolkit profile and Tell the app (phase 5) | Waiting: empty in `.env` |
| `HF_TOKEN` | Optional: faster model downloads | Optional |

Set in `.env`: `APP_TOKEN`, `INTERNAL_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TYPESAFE_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`.

## Deploy the server

```bash
npm run deploy
```

This pushes `.env` into the Modal secret `my-voice-env`, deploys the Modal app `my-voice`, prints the server URL and writes
`app/.env`. For demo day set `KEEP_WARM=1` in `.env` and deploy again (one container stays on; costs GPU time).

Check it: `npm run smoke` (every demo flow against the deployed server) and `node scripts/handshake.mjs` (hello → ready time).

## Run the app on the iPhone (development build)

One-off setup, from the repo root:

```bash
cd app
npx eas-cli login
npx eas-cli device:create
npx eas-cli build --profile development --platform ios
```

`device:create` gives a link: open it on the iPhone to register it. When the build finishes, open its install link on the
iPhone. Enable Developer Mode on the iPhone if iOS asks (Settings → Privacy & Security → Developer Mode).

Each session:

```bash
cd app
npx expo start --dev-client
```

Open the My Voice app on the iPhone and pick the server shown (same Wi-Fi), or scan the QR code with the camera. If the phone
can't reach the computer, use `npx expo start --dev-client --tunnel`.

## Run the app in a browser (for checks without the phone)

```bash
cd app
npx expo start --web
```

## Developer panel

Settings → long-press the version line. Server URL, app token, active speaker (`P1` for testing, `S1` for the co-designer),
thresholds, end-of-speech silence and partials.

## Import team data

The team's folders are read straight from the `speech-data` volume (`<SPK>/clips.csv`, `<SPK>/incoming/`, `<SPK>/wav/`),
or from a local `hack-speech/` download:

```bash
cd server
modal run jobs.py::import_team --speaker S1
modal run jobs.py::import_team --speaker S1 --folder ../hack-speech
```

Import keeps the team's ids, split, condition and ok flags, converts audio to 16 kHz mono wav, re-freezes the test set
(with babble versions) and scores stock Whisper plus every registered model. One-off prerequisites:

```bash
cd server
modal run jobs.py::build_noise_bank
modal run jobs.py::build_prompts
```

A teammate's adapter on the `speech-models` volume root (for example `p1-test`) is registered and activated only if it
beats the active model:

```bash
cd server
modal run jobs.py::register_adapter --name p1-test --speaker P1
```

## Train and evaluate

```bash
cd server
modal run jobs.py::train --speaker S1
modal run jobs.py::eval_asr --speaker S1
modal run jobs.py::eval_pipeline --speaker S1 --providers jev,openai
```

`train` is the same as Improve now in the app: it trains from the base model on every trainable clip (never a test
clip), scores every test condition, promotes only if mean WER drops by 0.5+ points without quiet WER rising by more
than 1, and hot-swaps the server's adapter. `eval_pipeline` replays his test clips through the whole turn and stores
the speak-threshold curve per decision model; the Results screen shows it.

Automatic retraining starts after 20 new trainable clips once he has been quiet for 2 minutes.

## Calls

- **App calls (no keys needed):** Calls tab → share "Your call code" or the link `/c/<code>`. The other person opens it
  in any browser, taps Call; his app rings.
- **Phone calls:** set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` in `.env`, then `npm run deploy`.
  A trial account can only call numbers verified in the Twilio console, and plays a trial notice first. A UK number needs
  Twilio's regulatory approval (days); any number already on the account works. Emergency numbers are blocked.

## Checks

```bash
npm run doctor
npm run verify
cd server && uv run pytest -m live
```

`doctor` calls each provider once with the keys in `.env`. `verify` typechecks the app, runs the server tests and the
smoke flows against the deployed server. The live tests call Jev, OpenAI and Anthropic for real.

## Experiments (lips and realtime voice)

Off unless the server flag is set; even then each one is off until he switches it on in Settings → Experiments.

```bash
REALTIME_VOICE=1 LIPS=1 npm run deploy   # or put REALTIME_VOICE=1 and LIPS=1 in .env so every deploy keeps them
npm run deploy:web                         # the iPhone uses the web build
```

Measured numbers for each acceptance check: `GET /experiments/report?speaker=P1` (the Experiments screen shows them).

### R1 streamed voice

On the iPhone: Settings → Experiments → Stream my voice on → tap anywhere once (unlocks sound) → Talk 20 sentences.
The Experiments card then shows the middle time from the text appearing to the first sound (target 350 ms over 20).
From the computer: `node .work/probes/r1_turns.mjs 3` (P1 recordings through live turns) and the smoke flow `R1`.

ElevenLabs offers zero data retention only on enterprise plans; streamed text is processed like the whole-clip voice.

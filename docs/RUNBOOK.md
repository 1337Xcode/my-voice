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

# SPEC: personal speech translator

Version 1, 7 November 2026. Owner: Darshan. Working name "My Voice" (change it with him).

## 0. How to use this spec

- This file is the source of truth. Read all of it before building. `docs/TEAM.md` (the team contract) describes the files teammates produce; stay compatible with it.
- Build the phases in section 17 in order. Every phase ends with the app and server running and its acceptance checks passing.
- This spec says what to build and the contracts between parts. It holds no code. Choose the implementation, and check every library, SDK and API against its current docs before using it. If something named here doesn't exist or doesn't work as described, use the closest working option and record why in `docs/DECISIONS.md`.
- Build against the real services. No mocks, no seeded fake data, no demo mode. If a key is missing, build that path fully, note it in `docs/RUNBOOK.md` as waiting for the key, and move on.
- Speaker `P1` is the developer's own voice for testing. Speaker `S1` is our co-designer. Never write a real name or any health or diagnosis detail in code, data, logs, prompts or the toolkit profile.

## 1. Who it's for and what it must do

Our co-designer's speech is hard for others to follow: a familiar listener catches roughly 10 to 20% of his words and stock speech recognisers do worse. He uses Akoli Speech today and finds it slow and unreliable with people talking nearby.

The app listens to him, works out what he said using a speech model trained on his own voice plus context, and shows the sentence in very large text while speaking it in a clear voice he chose. When it isn't sure, it never guesses out loud: it shows him up to three options to tap, or asks him to say it again. Every sentence he confirms or corrects teaches it, immediately for repeated phrases and corrections, and through retraining for everything else.

His four asks, each a measured target in section 2:

1. Faster than Akoli.
2. Works with people talking nearby.
3. Understands far more of his words.
4. Works on phone calls.

Two more come from him wanting it dead simple: useful within ten minutes of first opening it, and it must never say a wrong sentence it was unsure about.

The design follows one finding: people with very atypical speech get far better recognition from a model personalised on their own recordings than from any general model. Personal models beat expert human listeners on short phrases, and most of the gain comes from the first few minutes of data ([Green et al.](https://research.google/pubs/automatic-speech-recognition-of-disordered-speech-personalized-models-outperforming-human-listeners-on-short-phrases/), [Euphonia](https://research.google/blog/personalized-asr-models-from-a-large-and-diverse-disordered-speech-dataset/)). For atypical speech, fine-tuning plus LLM error correction cut Whisper's errors substantially ([Folkertsma et al. 2026](https://arxiv.org/abs/2605.15854)).

## 2. Targets

All times are measured from the end of his speech: the moment he taps Done, or the moment the server detects silence. Section 15 says how each is measured.

| Target | Value |
| --- | --- |
| Text on screen, confident turns | Median 0.8 s or less |
| Text on screen, all turns | Median 1.4 s, 95th percentile 2.2 s |
| Voice starts | Median 1.8 s or less |
| Saved phrase tapped to voice | 0.3 s or less, offline too |
| Words understood on his held-out sentences (quiet) | Higher than new listeners, and higher than the familiar listener once he has 100 or more training clips |
| Words understood in babble (5 dB) | Within 10 points of quiet |
| Wrong sentences spoken without asking | Under 2% of spoken turns |
| Turns where it asks him to pick or repeat | Under 25% at first, falling as it learns |
| Crash-free sessions | No crash in a 30-minute session |

## 3. What must work at the demo

These moments decide what to prioritise. Each must work live, with his real model.

1. He says one of his saved phrases. It appears in large text and is spoken about a second later.
2. He says a new sentence. The app either speaks it, or shows three options. He taps the right one, it's spoken, and a small "Learned" note appears.
3. He says that same sentence again, and it's understood straight away.
4. The Results screen shows words understood: new listeners, stock Whisper, and his model, in quiet and in babble.
5. He tells the app, in his own speech, "make the text bigger". A confirm card appears. He accepts, the text grows, and his toolkit profile shows the change.
6. If calls are built: he calls a teammate's phone. They hear the clear voice and he sees their reply as captions.

## 4. Architecture

Four parts, deliberately few.

| Part | Runs on | Does |
| --- | --- | --- |
| Mobile app | Expo development build on iPhone (Android later) | Captures audio, shows text and options, plays the voice, Teach, Phrases, Calls, Settings, offline phrases |
| Speech server | One Modal app: a GPU class serving FastAPI over HTTPS and WebSockets | Endpointing, speaker gate, personal ASR, phrase matcher, correction memory, LLM repair, decision gate, TTS, calls bridge, logging, evaluation |
| Trainer | Modal GPU function in the same Modal app | Trains a LoRA adapter on his clips, evaluates it, promotes it only if it's better |
| Storage | Two Modal Volumes: `speech-data` and `speech-models` | Clips, labels, phrases, memory, logs, models, evaluation |

External services:

| Service | Used for | Sees his audio? |
| --- | --- | --- |
| Anthropic API, model `claude-haiku-5-5` | Repairing the recogniser's guesses; mapping "Tell the app" requests to settings; suggesting Teach sentences | No, text only |
| OpenAI Decisions API, model `gpt-6-luna` | Calibrated choice between candidate sentences (speak or ask) | No, text only (the API doesn't accept audio) |
| ElevenLabs, model `eleven_flash_v2_5` | The clear voice | No, text only |
| Twilio Programmable Voice with Media Streams | Phone calls to ordinary numbers | Callee audio only, never stored |
| AI for Accessibility toolkit server | Reading and writing his preferences profile | No |

The serving class must run at most one container (`max_containers` 1) with concurrent inputs enabled. All WebSockets (his app session and the Twilio media stream) must land in the same container so audio can be bridged in memory. It's a single-user system.

Serving uses a GPU with at least 24 GB (A10G or L4). Training uses A10G or L40S. Keep the serving container warm while the app is in use. The app calls a wake route on launch, and a scaledown window of about 15 minutes applies. A deploy-time setting `KEEP_WARM=1` keeps one container always on for demo day.

## 5. Repository layout

| Path | Contents |
| --- | --- |
| `app/` | Expo app, TypeScript |
| `server/` | Modal app, Python: web API, pipeline, models, trainer, evaluation, CLI entrypoints |
| `server/assets/` | Default phrase list, Harvard sentence lists, babble bank build script |
| `docs/SPEC.md` | This file |
| `docs/TEAM.md` | Team contract |
| `docs/DECISIONS.md` | Every choice the build made that this spec didn't fix |
| `docs/RUNBOOK.md` | How to deploy, run on a phone, import team data, train, evaluate, and what's waiting on keys |
| `.env.example` | Every variable in section 6 |

## 6. Accounts, keys and environment

Use our own keys, never the event's shared keys: those aren't set up for sensitive data.

| Variable | Where | Purpose |
| --- | --- | --- |
| Modal token (from `modal setup`) | Developer machine | Deploy and run |
| `APP_TOKEN` | Modal Secret, and the app's public env | Shared bearer token between app and server |
| `ANTHROPIC_API_KEY` | Modal Secret | Haiku 5.5 |
| `OPENAI_API_KEY` | Modal Secret | Decisions API. Use zero data retention and EU processing if the account is eligible |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_DEFAULT_VOICE_ID` | Modal Secret | Voice |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | Modal Secret | Calls |
| `TOOLKIT_URL`, `TOOLKIT_TOKEN` | App public env | Toolkit server and an `aat_` app or default token |
| `HF_TOKEN` (optional) | Modal Secret | Model downloads, if needed |
| `EXPO_PUBLIC_SERVER_URL` | App public env | The Modal web URL |
| `KEEP_WARM` | Deploy-time | 1 on demo day |

Model ids: confirm `eleven_flash_v2_5` against ElevenLabs' models endpoint, and `claude-haiku-5-5` and `gpt-6-luna` against the vendors' docs. If any has changed, use the current low-latency equivalent and note it in DECISIONS.

## 7. Storage and data formats

Everything is keyed by speaker id (`S1`, `P1`). One speaker is active at a time; the developer panel switches it.

### 7.1 Volume `speech-data`

| Path | Contents |
| --- | --- |
| `<speaker>/raw/` | Original uploaded or imported files, unchanged |
| `<speaker>/audio/<clip_id>.wav` | 16 kHz mono 16-bit PCM, peak-normalised, leading and trailing silence kept up to 200 ms |
| `<speaker>/clips.jsonl` | Clip records (7.3), append-only; the last record for an id wins |
| `<speaker>/phrases.json` | Phrase bank (7.4) |
| `<speaker>/vocab.json` | Names, places and words he uses, for prompts |
| `<speaker>/memory.jsonl` | Correction memory (7.5) |
| `<speaker>/turns.jsonl` | One record per turn (7.6) |
| `<speaker>/settings.json` | Server-side copy of preferences the pipeline uses |
| `<speaker>/eval/` | Imported listener, Akoli and test-log CSVs; evaluation outputs; synthetic noisy test audio |
| `<speaker>/tts/` | Cached voice audio for phrases, per voice id and format |
| `_shared/noise/babble/` | Babble bank (section 9.4) |
| `_shared/prompts/` | Harvard lists and default phrases |

### 7.2 Volume `speech-models`

| Path | Contents |
| --- | --- |
| `<speaker>/<model_name>/` | PEFT LoRA adapter, processor files, `meta.json` (base model id, created time, training clip count and ids, hyperparameters, metrics per test condition, per-clip results) |
| `<speaker>/registry.json` | All versions with metrics, the `active` version, and the stock baseline metrics |
| `<name>/` at the volume root | Adapters made by the teammates' script. Register them before use (section 12.3) |

Model names: `<speaker lowercase>-whisper-lora-v<N>`, for example `s1-whisper-lora-v3`. This matches the team contract.

### 7.3 Clip record

The first eight fields are the team contract's `clips.csv` columns, unchanged. The import reads that CSV directly.

| Field | Values |
| --- | --- |
| `id` | Unique. Team ids are kept (`t01`, `r001`, `t01n`). App ids: `ta01` to `ta10` for onboarding test sentences; `c-<timestamp>` for everything else |
| `speaker` | `S1`, `P1` |
| `text` | The label: exactly what he said |
| `file` | Filename in `raw/` (imports) or the wav name |
| `split` | `train` or `test` |
| `condition` | `quiet` or `noisy` |
| `ok` | true or false (the team CSV's `yes` or `no`) |
| `notes` | Free text |
| `source` | `teach`, `import`, `use`, `review` |
| `trust` | `read` (prompt read aloud), `explicit` (he picked or typed the right sentence), `reviewed` (approved in Review), `implicit` (auto-spoken, not challenged) |
| `phrase_id` | Set when the clip is an utterance of a bank phrase |
| `turn_id` | Set when the clip came from a live turn |
| `duration_s`, `created_at` | |
| `excluded` | true removes it from training and templates without deleting it |

Trainable clips are `ok` true, `split` train, not excluded, and trust `read`, `explicit` or `reviewed`. `implicit` clips are never trained on until he reviews them.

### 7.4 Phrase bank entry

`id`, `text`, `category` (Social, Café and shop, Phone, Getting around, Home, Mine), `order`, `pinned`, `template_clip_ids` (at most 5), `tts` (cached file per voice id and format), `uses` (count). Phrases are editable, reorderable and deletable. Deleting a phrase keeps its clips as ordinary training clips.

### 7.5 Correction memory entry

`heard` (ASR top-1), `nbest` (up to 5), `meant` (final text), `source` (pick, typed, review), `created_at`, `count` (how often this pair recurred).

### 7.6 Turn record

`turn_id`, `speaker`, `mode` (talk, handsfree, call, tell), `model_version`, `audio_kept` (true only if "Learn from my conversations" is on), and these timestamps in server milliseconds: `t_first_audio`, `t_end_of_speech`, `t_asr`, `t_phrase`, `t_round1`, `t_repair`, `t_round2`, `t_result_sent`, `t_tts_first_byte`, `t_tts_done`. Also client-reported `ms_end_to_text` and `ms_end_to_audio`; `candidates` (text, sources, ASR score, phrase score, decision probability); `action` (speak, pick, again, ignored); `final_text`; `outcome` (spoken, confirmed, picked, typed, rejected, said_again, cancelled).

## 8. One turn, end to end

This is the core of the product. Section 2 sets its latency budget.

### 8.1 Capture

- The app captures 16 kHz mono through `@siteed/audio-studio` (version 3, formerly `@siteed/expo-audio-studio`), which streams PCM in real time in Expo development builds. Request float32 or raw frames at about a 100 ms interval, convert to 16-bit little-endian PCM, and send each 100 ms frame (3,200 bytes) as a binary WebSocket message.
- Teach recordings go through exactly the same capture path and settings as live use. The model must learn the same sound it later hears.
- Half duplex: capture pauses while the app plays a voice, so the recogniser never hears our own output.
- Show a live input level from the client so he can see he's being heard.

### 8.2 Endpointing

- Default mode is tap to talk. He taps Talk, speaks, and taps Done; Done ends the turn instantly. If he doesn't tap Done, the server ends the turn after a silence of 900 ms, adjustable from 500 to 2,000 ms because he may pause mid-sentence.
- The server runs Silero VAD on the incoming frames. Ignore turns with under 250 ms of detected speech (reply `ignored`, reason `too_short`).
- If a turn runs past 30 seconds, end it and process what arrived.

### 8.3 Speaker gate (hands-free mode only, phase 7)

Compute an ECAPA speaker embedding (SpeechBrain `spkrec-ecapa-voxceleb`) for each segment. Compare it with his enrolment centroid, built from 10 or more of his clips. Pick the threshold on his clips against impostor speech (P1 and LibriSpeech speakers) so that at most 1% of his own segments are rejected. Below threshold, the segment is someone else: in hands-free mode it becomes a partner caption (8.11), never his sentence. In tap-to-talk mode, everything in his turn is his.

### 8.4 Three recognisers, run in parallel when the turn ends

**A. Personal ASR.** Base `openai/whisper-large-v3-turbo` (MIT) with his active LoRA adapter, or no adapter before his first model. English, transcribe, no timestamps, temperature 0, beam size 5, return the 5 best hypotheses with length-normalised log-probabilities.

Guard against Whisper's known hallucinations on silence and noise:
- Drop a hypothesis when no-speech probability is high or the compression ratio is extreme.
- Keep a blocklist of stock filler outputs (for example "Thank you for watching").

His vocabulary as a decoder prompt is optional. Turn it on only if it lowers error on his test set.

Keep the base model loaded and hot-swap adapters between turns. Target: 400 ms or less for a 6-second utterance on the serving GPU.

**B. Phrase matcher.** Speaker-dependent template matching for his phrase bank, so phrases work from the first two recordings with no training.
- Features: frame-level hidden states from a middle layer of `microsoft/wavlm-base-plus` (start at layer 6; pick the layer with the best leave-one-out accuracy on his clips). Normalise per utterance and trim silence with the VAD.
- Distance: dynamic time warping with cosine distance, a band constraint, normalised by path length. A phrase's distance is the minimum over its templates.
- Output: the top 3 phrases with distance, a softmax score across phrases, and the margin to the runner-up. Reject everything when the best distance exceeds a threshold learned from his within-phrase distances (95th percentile, recomputed as templates change).
- Target: 80 ms or less for 50 phrases with 3 templates each.

This rests on two kinds of evidence: classic speaker-dependent template recognition for atypical speech, and recent prototype-based few-shot work on self-supervised features, which cut unseen-speaker word error from 43% to 27% with no fine-tuning ([PB-DSR](https://arxiv.org/html/2407.18461v1)). Its accuracy for him is measured, not assumed (section 15).

**C. Correction memory.** Look up the 5 stored pairs whose `heard` is most similar to the current ASR top-1 (normalised character edit distance). If a stored `meant` sentence was confirmed two or more times and its similarity passes a threshold, add it as a candidate with source `memory`.

### 8.5 Candidate set

Merge A, B and C into at most 10 candidates, de-duplicated after text normalisation. Each candidate keeps all its sources and scores:
- ASR rank and log-probability
- phrase score and margin
- memory similarity and count
- how many sources agree on it

### 8.6 Round 1: the decision gate (OpenAI Decisions)

Call `POST /v1/decisions` with model `gpt-6-luna` ([docs](https://developers.openai.com/api/docs/guides/decisions)).

**`input`:** one user message with `input_json` holding these, in this order:
1. Static content first, for implicit caching (it needs a shared prefix of 1,024 tokens or more): his phrase bank, his vocabulary, and an articulation note. The note says: "the recogniser most often confuses consonants made with the tongue (t, d, n, l, s, z, k, g, r, sh, ch); vowels and lip sounds (p, b, m, f, v, w) are more reliable". Keep it as a fact about sounds, never a diagnosis, and update it from his correction statistics once there are 30 or more corrections.
2. Then the conversation so far (the last 6 turns: his final sentences, plus partner or callee captions when present).
3. Then the candidates with their features.

**`questions`:** one `choice` question named `meant`. Its choices are each candidate id plus `none`, each with the sentence as its description. The instructions, in substance: "Which sentence did this speaker most likely say? Weigh recogniser agreement and scores, phrase-match strength, whether it fits the conversation, and his known phrases. Choose none if no candidate is likely."

**Response:** `answers[0].probabilities` per choice, and `confidence`.

### 8.7 Repair: Haiku, started in parallel with round 1

Call `claude-haiku-5-5` with:
- the same static block (cached with prompt caching)
- up to 5 correction memory pairs as examples ("when the recogniser heard X, he meant Y")
- the conversation
- the 5-best list with scores
- the phrase matches

Ask for up to 3 repaired sentences as structured output. Every sentence must be explainable from at least one hypothesis or phrase match. Fix misheard words, don't add meaning he didn't express, keep his phrasing, and use British spelling. Timeout: 1.2 s. On timeout, carry on without repairs.

This is generative error correction from the n-best list, which cut errors substantially on atypical speech ([GER](https://arxiv.org/html/2505.20163v1)).

### 8.8 Act

Thresholds:
- `speak_threshold`: default 0.85, tuned per section 15.4.
- `pick_threshold`: default 0.55.

Steps:
1. **Round 1 confident.** If the top non-`none` probability is at least `speak_threshold`, act now: send `result` with action `speak`. When the Haiku call returns, discard it.
2. **Round 2.** Otherwise wait for repair, add repaired sentences as candidates (source `repair`), and call Decisions again with the full set.
3. **Speak.** Top probability at least `speak_threshold` and the setting is "Speak straight away": action `speak`. With "Check with me first": action `pick`, with the top candidate shown as the first card.
4. **Pick.** Top three non-`none` probabilities sum to at least `pick_threshold`: action `pick` with those three, ordered by probability.
5. **Again.** Otherwise: action `again`. The app asks him to say it again, offers typing, and shows the top candidate small and greyed out, tappable.

### 8.9 Voice

The server calls ElevenLabs `POST /v1/text-to-speech/{voice_id}/stream` ([docs](https://elevenlabs.io/docs/api-reference/text-to-speech/stream.md)):
- model `eleven_flash_v2_5`
- format `mp3_44100_128` for the app, or `ulaw_8000` for calls
- speed taken from his speech-rate preference

For speaking turns, start TTS as soon as the action is known, in parallel with sending `result`. Send the finished clip to the app as one `audio` message. If voice-start median exceeds 1.8 s, switch to streamed playback and note it in DECISIONS.

Cache audio by (voice id, format, text). Pre-synthesise every phrase in his chosen voice whenever the bank or voice changes, and download it to the phone for offline one-tap playback.

### 8.10 Partial words (optional display)

While he speaks, once the buffer passes 1 s, decode greedily every 700 ms with the same model and send `partial`. Skip a partial if the previous one is still running. Show partials only when a personal model is active: stock partials on his speech are noise and would only distract him.

### 8.11 Partner captions (phase 7)

Two sources:
- In hands-free mode, segments the speaker gate rejects.
- In tap-to-talk mode, while he holds a "Them" button.

Both are transcribed with stock Whisper (no adapter) and shown small at the top of Talk. They go into the conversation context for 8.6 and 8.7. Partner audio is never stored.

### 8.12 Logging

Write the turn record (7.6) for every turn, including ignored ones. The app reports `client_timing` after playback starts.

## 9. Learning

### 9.1 What every turn teaches, instantly

| Event | Instant effect | Training label |
| --- | --- | --- |
| He picks an option or types the right sentence | Adds a memory pair; if the sentence is a bank phrase, adds the turn audio as a template (keeping the 5 most recent) | Clip with trust `explicit` (if audio is kept) |
| He taps "Not what I meant" on a spoken sentence | Opens Pick with the other candidates plus Type | Same as above once he chooses |
| Auto-spoken, not challenged | Counts toward that sentence's frequency | Clip with trust `implicit`, held for Review |
| He approves in Review | Becomes trainable | Trust `reviewed` |
| He rejects in Review | Clip excluded | None |
| He says the same confirmed sentence 2 or more times | Becomes a memory candidate source | |

Show a small, quiet "Learned" note in Talk after any explicit correction.

### 9.2 Review

Teach shows a Review list of implicit turns. Each item has the sentence, a play button for his audio, and ✓, ✗ and Edit. One tap each, and it can be done in batches. This is the safe way to turn everyday use into training data without wrong-but-unchallenged sentences poisoning the model.

### 9.3 Retraining

**Triggers:**
- He taps "Improve now".
- Onboarding finishes.
- 20 or more new trainable clips have arrived since the last run, and no turn has happened in the last 2 minutes.

**Data:** all trainable clips (7.3), never any test clip. Assert there's no overlap and log the counts. Hold out 10% of training clips (at least 4) for validation.

**Augmentation**, applied on the fly to each training example:
- speed change of 0.9, 1.0 or 1.1
- with probability 0.5, babble mixed in at a random SNR between 0 and 15 dB
- light SpecAugment

**LoRA:**
- rank 32, alpha 64, dropout 0.05
- on attention query, key, value and output projections in encoder and decoder
- learning rate 1e-4, cosine schedule, 10 warmup steps
- effective batch 16, fp16 or bf16, fixed seed
- up to 15 epochs, early stopping on validation WER with patience 3

Train from the base model each time, on all current data, not on top of the previous adapter.

**Evaluate** on every test condition (15.1).

**Promote** only if:
- the mean WER across conditions is at least 0.5 points lower than the active model's, and
- quiet WER is not more than 1 point worse.

Otherwise keep the active model and tell the app "Not better yet; keeping v<N>".

**On promotion:** write the registry and commit the volume. Then call the server's internal reload route; the server reloads the volume, swaps the adapter between turns, and pushes `model_update`.

**Time:** under 6 minutes end to end for 300 clips. Progress is visible in the app.

### 9.4 Babble bank

A one-off command builds 20 babble tracks of 30 s each. Each mixes 6 random speakers from LibriSpeech dev-clean (CC BY 4.0), loudness-normalised. Store them in `_shared/noise/babble/`. The same bank makes the synthetic noisy test sets (15.1).

### 9.5 Teach prompts, in order

1. His phrase bank. Each phrase twice: the first is a template; the second goes to the phrase test set the first time, and becomes a template after that.
2. Harvard sentences, lists 2 onward (list 1 is the test set). Fetch the lists from the IEEE 1969 set at build time and store them in `_shared/prompts/`.
3. "Sentences like yours": Haiku generates short everyday sentences in the style of his bank and recent confirmed sentences (text only), avoiding health topics.

## 10. First run: useful in ten minutes

1. **Welcome and consent.** Plain words, one screen. What we record, where it's stored (his phone and our server), that LLMs see text only, that he can delete everything, and a yes or no for "Learn from my conversations".
2. **Pick a voice.** Play 4 to 6 ElevenLabs voices on the same sample sentence and let him choose.
3. **Phrases.** Show the default bank (section 11.8) and let him delete, edit or add phrases by typing. He can come back later.
4. **Test sentences first.** Record Harvard list 1 (11.9) once each as `ta01` to `ta10`, split test. Then freeze the test set. The server creates the synthetic noisy versions.
5. **Phrase recordings.** Record each phrase twice (the minimum to finish is his first 15 phrases). Phrase mode works the moment a phrase has one template.
6. **Make my model.** Training v1 starts. While it runs (about 5 minutes) he can already use phrases, and open sentences use the stock model behind the gate.
7. **Done.** The app shows "Your model v1: understands X% of words on your test sentences (stock: Y%)".

Every step can be skipped and resumed from Teach. Total recording time to finish the minimum: about 6 minutes.

## 11. The app

### 11.1 Platform

- Expo, latest stable SDK, TypeScript, file-based routing, development build (native audio means Expo Go won't work). iOS first, built from the Mac to his iPhone; Android must not be broken by design choices but isn't tested today.
- Audio: `@siteed/audio-studio` for capture, `expo-audio` for playback, `expo-speech` for offline typed speech, and `expo-haptics`.
- The WebSocket uses React Native's built-in client with binary frames.
- Local storage: offline phrase cache, contacts, settings, and the last 50 turns.
- iOS: microphone permission text in plain words; background audio mode, so calls survive a locked screen.

### 11.2 Navigation

Four tabs: Talk, Phrases, Teach, Calls. Settings opens from a gear on Talk. A hidden developer panel (long-press the version number in Settings) holds the server URL, token, active speaker (`S1`/`P1`), thresholds, the endpoint silence and the partials flag.

### 11.3 Talk

The main screen. One large primary button sits at the bottom centre, reachable one-handed.

| State | What he sees and can do |
| --- | --- |
| Idle | Big Talk button; a row of his 6 most-used phrases as large chips; Type button; small "Tell the app" button; small "Them" button (phase 7); connection and model badge (for example "v3 · ready") |
| Listening | Live level meter and "Listening"; partial words in grey if enabled; big Done button; Cancel |
| Thinking | The level freezes; a subtle progress line. If over 3 s: "Taking a moment", plus Type |
| Speaking | The sentence in very large text (32 pt minimum, scaled by his text size), a speaking indicator, Replay, "Not what I meant", and a Flip button that rotates the sentence 180 degrees for the person opposite |
| Pick one | Up to 3 large cards, most likely first; tapping one speaks it. "Say again" and Type below |
| Say again | "I didn't catch that. Say it again, or type it." The top guess is shown small and greyed, and is tappable |
| Ignored | Brief note "Didn't catch any speech" (or "Someone else was speaking" in hands-free), then back to Idle |
| Offline | Banner "No connection: phrases and typing still work". Talk is disabled; phrase chips play cached audio; typed text uses the phone's voice |
| Learned | After a correction, a small note for 2 s: "Learned" |

Conversation strip: the last few turns above the main area, small. His sentences are on one side and partner captions on the other.

### 11.4 Phrases

- His bank by category, as large buttons; one tap speaks the cached audio (offline too).
- Edit mode: add (type the text, then record 2 templates), rename, reorder, delete, pin.
- Each phrase shows a small dot for templates recorded (0, 1, 2+).

### 11.5 Teach

- **Your model card:** active version, words understood on his test sentences (quiet and babble), against stock; trend sparkline across versions; clips trained on; Improve now with live status (queued, training, evaluating, promoted or not better).
- **Record:** the next prompt in very large text, Record and Stop (same capture path), Play back, Keep or Redo, Skip. Progress: clips today, total minutes.
- **Review:** count badge; the list described in 9.2.
- **Results:** a link to the Results screen (15.3).

### 11.6 Calls

- **Contacts:** a name and number he enters, stored on the phone only. Emergency numbers (999, 112, 911) are blocked with a note to call directly or use emergencySMS.
- **Call screen:** status (dialling, ringing, connected with timer, ended, failed with a reason); callee captions as a live list; his Talk controls exactly as in Talk; a quick phrase row; Hang up.
- **Opening line:** optional, set once, spoken when the callee answers. For example: "Hi, this is [first name he chooses]. I use a speech app, so there'll be short pauses." It contains no medical detail.

### 11.7 Settings (exactly five)

1. **Voice:** pick from voices, with a sample play. A later "Your own voice" entry is shown disabled with a note.
2. **Before speaking:** "Speak straight away" or "Let me check first".
3. **Text size:** large, extra large or huge.
4. **Microphone:** shows the active input. Lets him choose phone or a connected mic if the audio library supports input selection; otherwise the system default with a note.
5. **My data:** Learn from my conversations (on or off); Export everything (zip); Delete everything (type DELETE to confirm).

The toolkit sync status shows as a single line under these when configured (section 14).

### 11.8 Default phrase bank

He edits this on first run:

| Category | Phrases |
| --- | --- |
| Social | Hello, nice to meet you. / Thank you very much. / Sorry, can you say that again? / I use this app to help me speak. / Just a moment, please. / Yes, please. / No, thank you. / I'm fine, thanks. How are you? / See you later. / Have a good day. |
| Café and shop | Can I have a flat white, please? / Can I have a cup of tea, please? / Can I pay by card? / Just this, thank you. / A table for one, please. / Can I see the menu? / The bill, please. / Where is the toilet, please? |
| Phone | Could you speak a bit slower, please? / Can you send me that by text? / I'd like to book an appointment. / I'm calling about my order. / What time do you open? |
| Getting around | Where is the station, please? / A return ticket, please. / Which stop do I get off at? |
| Home | Can you help me, please? / I need a moment. / I'll message you. |

### 11.9 Test sentences (Harvard list 1)

1. The birch canoe slid on the smooth planks.
2. Glue the sheet to the dark blue background.
3. It's easy to tell the depth of a well.
4. These days a chicken leg is a rare dish.
5. Rice is often served in round bowls.
6. The juice of lemons makes fine punch.
7. The box was thrown beside the parked truck.
8. The hogs were fed chopped corn and garbage.
9. Four hours of steady work faced us.
10. A large size in stockings is hard to sell.

### 11.10 Look and accessibility

- **Look:** muted warm greys, Geist type (SIL OFL), one restrained accent colour, and motion only for state changes. All motion is off when reduce motion is on (system setting or his toolkit profile).
- **Every element earns its place:** no explanatory text blocks, and no chat-window look.
- **Touch targets:** at least 48 by 48 points; the primary buttons at least 72.
- **Contrast and colour:** WCAG AA contrast at minimum, AAA in high-contrast mode. Never use colour alone for meaning.
- **Screen readers:** VoiceOver labels on everything; the big sentence is announced when it appears.
- **Feedback:** haptics on Listening start, result, Learned and errors.
- **Text:** respects the system text size and his chosen size, whichever is larger.

### 11.11 Errors and reconnects

- The WebSocket reconnects automatically with backoff. A turn interrupted by a disconnect says "Connection dropped, say it again" and offers Type.
- The first connect after idle shows "Waking up the speech server" with a spinner until `ready`.
- Error messages are plain sentences, never codes. Nothing ever fails silently.

## 12. Server interfaces

### 12.1 WebSocket `/ws`

Auth: bearer `APP_TOKEN` as a query parameter or header. Binary frames from the client are audio for the current turn; everything else is JSON with a `type`.

**Client to server:**

| Type | Fields | Meaning |
| --- | --- | --- |
| `hello` | `speaker`, `client_version`, `settings` | Session start, or after a reconnect |
| `start_turn` | `turn_id`, `mode` (talk, handsfree, call, tell, them) | Audio frames for this turn follow |
| `end_turn` | `turn_id` | He tapped Done |
| `cancel_turn` | `turn_id` | Discard |
| `choose` | `turn_id`, `candidate_id` or `text`, `via` (pick, typed) | His explicit choice; speak it |
| `confirm` | `turn_id` | ✓ on a check-first card; speak it |
| `reject` | `turn_id` | "Not what I meant" |
| `say_phrase` | `phrase_id` | One-tap phrase (when online; offline plays the cache locally) |
| `type_and_speak` | `text` | Typed sentence |
| `client_timing` | `turn_id`, `ms_end_to_text`, `ms_end_to_audio` | After playback starts |
| `ping` | | Keepalive every 15 s |

**Server to client:**

| Type | Fields | Meaning |
| --- | --- | --- |
| `ready` | `speaker`, `model_version`, `voice_id`, `features` (calls, toolkit, partials) | Session ready |
| `endpoint` | `turn_id` | Server detected end of speech |
| `partial` | `turn_id`, `text` | Live words |
| `ignored` | `turn_id`, `reason` (too_short, no_speech, not_speaker) | Nothing to say |
| `result` | `turn_id`, `action` (speak, pick, again), `candidates` (id, text, p, sources), `chosen_id`, `timings` | The decision |
| `audio` | `turn_id` or `phrase_id`, `format`, `data` (base64) | Voice clip |
| `learned` | `turn_id`, `kind` (memory, template) | Show the Learned note |
| `settings_proposal` | `turn_id`, `changes` (key, from, to, label) | For "Tell the app" (section 14) |
| `partner_caption` | `text`, `source` (room, call) | Captions |
| `call_status` | `call_id`, `state`, `detail` | Calls |
| `training` | `state`, `progress`, `eta_s`, `message` | Retraining status |
| `model_update` | `model_version`, `metrics` | After promotion |
| `error` | `code`, `message` | Plain message the app can show |

### 12.2 HTTP routes (all need the bearer token, except Twilio's webhook)

| Method and path | Purpose |
| --- | --- |
| `GET /health`, `POST /wake` | Liveness; warm the container |
| `GET /state` | Active model, registry summary, clip counts, Review count, settings, features |
| `POST /clips` | Upload a Teach recording: audio, prompt text, `phrase_id` if any, split, condition |
| `PATCH /clips/{id}` | Edit `text`, `ok` or `excluded` |
| `GET /phrases`, `PUT /phrases` | Read or replace the bank (also re-synthesises the voice cache) |
| `GET /tts/{file}` | Download cached phrase audio for offline use |
| `GET /teach/next` | The next prompt (9.5) |
| `GET /review`, `POST /review/{turn_id}` | List; approve, reject or edit |
| `POST /train`, `GET /train/status` | Start or watch retraining |
| `GET /results` | The Results screen data (15.3) |
| `POST /eval/run` | Re-run evaluation for all registered versions |
| `POST /settings` | Pipeline settings: voice, check-first, thresholds, endpoint silence |
| `POST /calls`, `POST /calls/{id}/hangup` | Start and end a call |
| `POST /twilio/voice` | Twilio webhook, returns TwiML |
| `WS /twilio/stream` | Twilio bidirectional media stream |
| `POST /internal/reload` | Trainer to server, after promotion (internal token) |
| `GET /export`, `DELETE /data` | His data |

### 12.3 Command-line entrypoints

| Command | Does |
| --- | --- |
| `deploy` | Deploy the Modal app |
| `build_noise_bank` | Section 9.4 |
| `import_team --folder <path>` | Reads a downloaded `hack-speech/` folder: `clips.csv`, `raw/`, `practice/`, `results/listeners.csv`, `results/test_log` if present. Converts audio and writes clip records with team ids, split, condition and ok unchanged. Re-freezes the test set to include new test ids, then runs evaluation |
| `register_adapter --name <n> --path <volume path>` | Registers an adapter made by the teammates' script, evaluates it on our test set, and activates it only if it beats the active model |
| `train --speaker S1` | Same as Improve now |
| `eval_asr --speaker S1` | WER per version per condition |
| `eval_pipeline --speaker S1` | Replays test clips through the whole turn pipeline (section 15.4) |
| `export --speaker S1`, `wipe --speaker S1` | His data |

## 13. Calls

Neither iOS nor Android lets an ordinary app hear a cellular call, so calls go through our server: the server places the call and bridges audio.

### 13.1 Flow

1. The app sends `POST /calls` with the number and contact name. The server creates a Twilio call from `TWILIO_FROM_NUMBER`. On answer, Twilio's webhook gets TwiML with `<Connect><Stream>`, which opens a bidirectional media stream to `/twilio/stream` with the call id as a custom parameter. The server links that stream to his app session.
2. **Callee audio** arrives as mu-law 8 kHz (inbound track). Decode it, upsample to 16 kHz, segment with the VAD, transcribe with stock Whisper, and send `partner_caption` with source `call`. Captions also feed the conversation context. Callee audio is never stored.
3. **His audio** comes from the app over his normal session in mode `call`, at full quality, not through the phone line. It runs through the normal pipeline. When a sentence is spoken (auto or picked), the server requests ElevenLabs `ulaw_8000` and sends it to Twilio as `media` messages without file headers, followed by a `mark`.
4. **While his turn is being processed**, the server sends a soft pulse tone to the callee every 1.5 s so they wait rather than talk over him. It sends `clear` before speaking the sentence.
5. **Opening line** and **quick phrases** are sent the same way, using cached `ulaw_8000` audio.
6. Hang up ends the Twilio call. `stop` from Twilio ends the session state, and the app shows Ended.

Message formats are per Twilio's [Media Streams WebSocket messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages).

### 13.2 Account limits to note in the runbook

- A Twilio trial account can only call verified numbers and plays a trial notice. The demo calls a teammate's verified phone.
- A UK number needs Twilio's regulatory approval, which can take days; any number already on the account works for the demo.
- Emergency numbers are blocked in the app and on the server.

## 14. Toolkit profile and "Tell the app"

The event's AI for Accessibility toolkit keeps a person's preferences in an Ability profile so every app that uses it adapts the same way. Its own FAQ says it can't yet understand speech that most speech software finds hard to recognise. Our personal recogniser fills exactly that gap, so he can set his profile by talking.

### 14.1 Connection

Every call is `POST {TOOLKIT_URL}/v1/librarian/{method}` with JSON body `{"args": [...]}` (positional) and `Authorization: Bearer {TOOLKIT_TOKEN}`. Responses are `{"ok": true, "result": ...}` or `{"ok": false, "error": ...}`.

Profile changes are announced by the server-sent events stream at `GET /v1/profile/events`: a `profile` event, then call `getProfile` to read the change.

Confirm each method's argument order against the toolkit repo's `server/API.md` (generated from the live route table) and `toolkit/API.md` before wiring it ([repo](https://github.com/AI-for-Accessibility-Collective/AI-for-Accessibility-Toolkit)). If `TOOLKIT_URL` isn't set, hide all toolkit features; local settings still work.

### 14.2 Read on launch and on every profile event

| Toolkit key | Our setting |
| --- | --- |
| `scalePercent` (or the profile's `textSize` need) | Text size |
| `highContrast` | High-contrast theme |
| `reduceMotion` | Motion off |
| `rate` (speech rate) | Voice speed |
| `largeTargets` | Larger buttons |
| `captions` | Partner captions on by default |

Read the effective preferences, plus our app's own scope `context:speech-translator` for `askBeforeSpeaking`, `whenUnsure` and `voiceId`.

### 14.3 Write back

When he changes a shared setting in our app, write it with `recordExplicitSetting(key, value, origin)`, with origin `speech-translator`. App-specific settings go through `recordScopedSettings` under scope `context:speech-translator`. Never write a condition or diagnosis: the profile records what he asks for.

### 14.4 "Tell the app"

1. He taps the small "Tell the app" button and speaks a request in his own words, for example "bigger text" or "always check with me first".
2. The turn runs through the normal recogniser in mode `tell`. The candidate sentence goes to Haiku, which maps it to changes from an allowed list only: text size, high contrast, reduce motion, voice speed, check first, voice.
3. The server sends `settings_proposal`. The app shows a confirm card listing each change in plain words.
4. On ✓, the app applies the changes and writes them to the toolkit. On ✗, it discards them. Nothing changes without his tap, which mirrors the toolkit's own consent-first proposals.

## 15. Evaluation and the Results screen

### 15.1 Test conditions

All built from frozen test clips, never trained on:

| Condition | Built from |
| --- | --- |
| `quiet` | His quiet test clips |
| `noisy_real` | Real noisy recordings, where they exist (team `t01n` and so on) |
| `babble_5db`, `babble_0db` | His quiet test clips mixed with babble from the bank, fixed seed, generated at freeze time |
| `phrases` | His held-out phrase repeats: phrase accuracy and reject rate for the phrase matcher |

### 15.2 Metrics

- **WER:** jiwer after Whisper's English text normaliser on both sides. "Words understood" is 100 minus WER, clamped to 0 to 100.
- **Systems:**
  - stock Whisper turbo
  - each registered model version
  - new listeners (listener ids starting `L` in `listeners.csv`, averaged)
  - familiar listener (`F`)
  - Akoli and any other system imported as a CSV of `id` and `hypothesis`
  - the full pipeline (15.4)
- **Live use:** from turn records. Medians and 95th percentiles of `ms_end_to_text` and `ms_end_to_audio`; ask rate; correction rate; the Data teammate's imported test log (right, close or wrong).

### 15.3 Results screen

1. **Headline:** one table of words understood, with systems as rows and quiet and babble 5 dB as columns. Each row shows n clips. New listeners, stock Whisper and his model are always present.
2. **Learning over time:** a line chart of words understood by model version.
3. **Live use:** speed (median text and voice times), how often it asked him, and how often it spoke a wrong sentence.
4. **Footnote:** test set size and what "words understood" means, in one line.

### 15.4 Gate calibration

`eval_pipeline` replays every test clip through the whole turn (empty context) and records the action and final text.

A spoken sentence counts as wrong if its WER against the reference is over 10%. For thresholds from 0.5 to 0.98, compute:
- wrong-but-spoken rate
- ask rate

Set `speak_threshold` to the lowest value with wrong-but-spoken under 2%. Store the curve and show the chosen point on Results. Re-run after every promotion.

## 16. Privacy and safety rules

- **Consent comes first.** Nothing is recorded until he says yes on screen. "Learn from my conversations" is a separate yes. With it off, live turns keep no audio.
- **Where his audio goes:** only to our Modal volumes and his phone. Anthropic, OpenAI and ElevenLabs receive text only, through our own keys.
- **No names or health details anywhere.** Use speaker ids. The opening line is his own text and stays on his phone.
- **Calls:** callee audio and transcripts are never stored on the server. Captions live on his phone for the call only.
- **Export and delete:** he can export or delete everything from Settings, and delete means everything, models included.
- **Never speak below threshold.** Every spoken sentence passed the gate or was chosen by him.
- **Emergency calls** are blocked, with a note to call directly or use emergencySMS.
- **No medical claims** anywhere in the app. It's a communication aid.

## 17. Build phases and acceptance checks

Each phase ends deployed, running on the iPhone, with its checks passing and the RUNBOOK updated.

| Phase | Builds | Done when |
| --- | --- | --- |
| P0 Skeleton | Repo layout, Modal app with `/health`, `/wake`, `/ws` handshake (`hello` and `ready`), volumes, secrets; Expo dev build on the iPhone with the four tabs and Settings shell; app connects and shows "ready" | The phone shows the server's `ready` within 60 s of a cold start, and within 2 s when warm |
| P1 Core loop | Capture and stream (8.1), endpointing (8.2), stock ASR n-best (8.4A), a gate-free stand-in that always returns action `pick` with the top 3 hypotheses so nothing is spoken until he taps (replaced in P3), TTS and playback with half duplex (8.9), Talk states Idle, Listening, Thinking, Pick one, Speaking, Ignored and Offline, phrase one-tap with cached audio online and offline, turn logging | With speaker P1, a spoken sentence shows up to 3 options and the tapped one is spoken; all stage timings are in `turns.jsonl`; offline phrase tap plays in under 0.3 s |
| P2 Personalise | Teach screen and `/clips`, onboarding (section 10), phrase templates and matcher (8.4B), babble bank, trainer with promotion and hot swap (9.3), Your model card, `import_team` and `register_adapter` | For P1: phrase leave-one-out accuracy is reported; v1 trains, evaluates and is promoted or rejected with metrics; the app shows the new version without restarting |
| P3 Gate and learning | Candidate set (8.5), Decisions rounds (8.6), Haiku repair (8.7), actions (8.8), Pick and Say again states, Check-first mode, correction memory (8.4C), Learned note, Review (9.2) | A deliberately misheard sentence leads to Pick, he picks, and saying it again yields that sentence through memory; the Review list fills and approving makes clips trainable |
| P4 Results | Evaluation commands, synthetic noisy tests, listener and Akoli imports, gate calibration (15.4), Results screen (15.3) | The Results screen shows stock vs model vs listeners, latency medians, and the calibrated threshold, all from real data |
| P5 Toolkit | Section 14: read, write, events, Tell the app | Changing text size in the app updates the toolkit profile, and changing it in the toolkit console updates the app within 5 s; "bigger text" spoken by P1 produces a confirm card and the change |
| P6 Calls | Section 13 | A call to a verified phone: the callee hears the opening line, then his sentences in the clear voice; he sees their captions; the pulse tone plays while he's being processed |
| P7 Hands-free | Speaker gate (8.3), hands-free mode toggle on Talk, partner captions (8.11) and the "Them" button, partials (8.10) | With two people talking, the other person's speech becomes captions and is never spoken; his speech still works |

## 18. Later (not in this build)

- Lip reading as a second input for crowded rooms. Audio-visual models cut errors sharply when other people talk ([AV-HuBERT](https://ai.meta.com/blog/ai-that-understands-speech-by-looking-as-well-as-hearing/)). It needs camera capture alongside audio, which risks audio-session conflicts on iOS, so it's kept out of today's build.
- His own voice from old recordings through the ElevenLabs Impact Program.
- A small offline model on the phone (whisper.rn), taught by his server model.
- A/B tests of Krisp background voice cancellation and the open Hush model on the babble set, kept only if his error drops.
- A model bake-off: Parakeet, Qwen3-ASR and Nemotron streaming against Whisper LoRA on his test set.
- Synthetic training clips from a clone of his own voice, kept only if real test error drops.
- Jev (TypeSafe AI) as the decision model through OpenRouter's Decisions API, compared with `gpt-6-luna` on gate calibration.
- Video calls through a desktop virtual microphone; more than one user.

## 19. References used by this build

- Personal ASR: [whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo), [PEFT](https://github.com/huggingface/peft), [jiwer](https://github.com/jitsi/jiwer)
- Phrase matching: [WavLM Base Plus](https://huggingface.co/microsoft/wavlm-base-plus), [PB-DSR few-shot prototypes](https://arxiv.org/html/2407.18461v1)
- VAD and speaker gate: [Silero VAD](https://github.com/snakers4/silero-vad), [SpeechBrain ECAPA](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
- Decision gate: [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions)
- Voice: [ElevenLabs streaming TTS](https://elevenlabs.io/docs/api-reference/text-to-speech/stream.md)
- Calls: [Twilio Media Streams messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages)
- Server: [Modal streaming Parakeet example (WebSocket on GPU)](https://modal.com/docs/examples/streaming_parakeet)
- App audio: [@siteed/audio-studio](https://deeeed.github.io/audiolab/docs/api-reference/recording-config)
- Toolkit: [AI for Accessibility Toolkit](https://github.com/AI-for-Accessibility-Collective/AI-for-Accessibility-Toolkit)
- Babble: [LibriSpeech (CC BY 4.0)](https://www.openslr.org/12)
- Test sentences: [Harvard sentences](https://www.cs.columbia.edu/~hgs/audio/harvard.html)

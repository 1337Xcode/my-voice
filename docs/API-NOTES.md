# API notes (researched 2026-11-07)

Every claim below comes from a page or package I fetched on 2026-11-07. Where I could not run a real call (no keys), I say "not run". Package versions are what `pip index` / `npm view` returned that day.

## Where the APIs differ from the first design

1. **Decisions choice shape.** Choices are `{ "value": string|boolean, "description": string? }`, not `{id, description}`. `choices` has 2 to 255 entries. The first design's "each candidate id plus `none`, each with the sentence as its description" maps to `value: "<candidate id>"`, `description: "<sentence>"`. There is no top-level `instructions`; each question has its own `instructions`. Shared instructions go in a `developer` message inside `input`.
2. **Decisions caching.** The implicit breakpoint sits at the end of the whole shared `input`. If the conversation and candidates are inside `input`, nothing is reusable after the first change. Fix: put only the static bank in `input` and the volatile parts in the question's `instructions` (an array of parts that may include `input_json`), or mark the static `input_text` part with `prompt_cache_breakpoint` and set `prompt_cache_options.mode = "explicit"`. `input_json` parts cannot carry a breakpoint. Question content never counts toward the 1,024-token prefix.
3. **Decisions probabilities** are an array `[{value, probability}]`, not a dict. Answers come back in question order and carry the question `name`.
4. **Installed `openai` Python 2.44.0 has no `client.decisions`.** `openai` 3.46.0 (latest on PyPI) has it. Upgrade, or call the REST endpoint with `httpx`.
5. **EU endpoint.** `https://eu.api.openai.com/v1` is documented as supporting `/v1/decisions` and `gpt-6-luna` (processing and storage in Europe). It only works for accounts that have data residency enabled (sales-gated) and a project created with region Europe; it costs a 10% uplift. Not run (no key).
6. **TypeSafe Jev is not Decisions-compatible.** Native endpoint is `POST https://api.typesafe.ai/v1/systemone` with body `{model, state, questions: {<id>: {...}}}` (questions is an object keyed by id; choice options are a `criteria` map). `jev-latest` is a valid alias (points to `jev-1.14.0`). The first design's line "Jev through OpenRouter's Decisions API" refers to OpenRouter's own alpha route `POST https://openrouter.ai/api/alpha/decisions`, which also uses TypeSafe's shape, not OpenAI's. DECIDE_MODEL must be handled by a separate adapter. See section 6.
7. **Anthropic.** Structured output is `output_config.format` with `type: "json_schema"` (GA, no beta header). Haiku 5.5 minimum cacheable prefix is **512 tokens** (not 1,024/2,048/4,096). Haiku 5.5 thinks adaptively by default at effort `medium`; for a 1.2 s budget send `output_config: {"effort": "low"}` and/or `thinking: {"type": "disabled"}`. Changing effort or `output_config.format` invalidates the prompt cache.
8. **ElevenLabs.** `eleven_flash_v2_5` is still current and listed (32 languages, about 100 ms, 40,000 chars). Newer `eleven_v4_turbo` (about 100 ms) and `eleven_v4` exist. `optimize_streaming_latency` is deprecated. The `/v1/voices` docs page now returns the v2 page (`GET /v2/voices`).
9. **Toolkit preference keys.** There is no flat list `scalePercent, textSize, highContrast, reduceMotion, rate, largeTargets, captions`. Those names come from the toolkit's *mobile surface output* (nested: `text.scalePercent`, `display.highContrast`, `motion.reduceMotion`, `speech.rate`, `touch.largeTargets`, `media.captions`). The keys you read and write through the Librarian are the **web settings registry** keys (`fontScale`, `contrastMode`, `motionReducer`, `speechRate`, `targetSize`, `showCaptions`, ...) and the **need dimensions** in `profile.fields.needs` (`textSize`, `contrast`, `reduceMotion`, `readAloudRate`, `captions`, ...). The first design needs a mapping table; see section 5.
10. **Toolkit `recordExplicitSetting(key, value, origin)`** passes `origin` as the `opts` object of `recordScopedSettings`. The code reads only `opts.scopeLabel` and `opts.writer` from it, so `origin: "speech-translator"` as a string is not used for scoping. It always writes scope `general`. For per-app settings use `recordScopedSettings("context:speech-translator", {...})` (scope regex `context:[a-z-]+`, so that name is valid).
11. **Modal GPU name.** The GPU guide lists `A10` (not `A10G`); `A10G` still appears in one guide example (volumes). Use `"A10"`, `"L4"`, `"L40S"`. Installed `modal` is 1.5.1; latest is 1.6.3. Modal also has a new `@app.server` decorator.
12. **Expo SDK is 58**, React Native 0.88.1, React 19.3.0 (released 2026-10-15). The release post said Expo Go for SDK 58 would reach the stores "within a few weeks"; irrelevant because the first design uses a development build.
13. **`@siteed/audio-studio` stream data.** On native, `onAudioStream` gives `event.data` as a **base64 string** by default (`streamFormat: 'raw'`), or a `Float32Array` with `streamFormat: 'float32'`. `pcm_8bit` is Android only. The old name `@siteed/expo-audio-studio` is a deprecated shim at 3.2.2 that re-exports `@siteed/audio-studio` 3.2.1. iOS default capture rate is 48 kHz; the library resamples to the requested 16 kHz.
14. **Whisper n-best.** For clips of 30 s or less, `generate(num_beams=5, num_return_sequences=5, return_dict_in_generate=True, output_scores=True)` returns a `ModelOutput` with `sequences` and `sequences_scores`. `compression_ratio_threshold`, `logprob_threshold` and `no_speech_threshold` are documented as long-form only; compute those checks yourself for the short-form n-best path.
15. **speechbrain.** `EncoderClassifier` is defined in `speechbrain.inference.classifiers`; `speechbrain.inference.speaker` re-exports it and the model card uses that path. Both work.
16. **silero-vad extras.** The `audio` and `all` extras pin `torchaudio<2.10`, but torchaudio 2.11.1 is current. Install plain `silero-vad` (needs only torch) and avoid the extras.
17. **Twilio.** Confirmed as described. `<Stream url>` cannot carry a query string; pass data with `<Parameter>` (combined name and value under 500 characters). Bidirectional streams only deliver the `inbound` track. The `connected` message has no `streamSid`; `start` does.

Nothing blocks the build. Open points that need a real call: EU endpoint access for the OpenAI account, whether Modal accepts `A10G` as an alias, and where exactly Twilio signs the WebSocket handshake URL.

---

## 1. OpenAI Decisions API

Sources:
- https://developers.openai.com/api/docs/guides/decisions (and `.md`)
- https://developers.openai.com/api/reference/resources/decisions/methods/create.md
- https://developers.openai.com/api/docs/guides/decisions-voice.md
- https://developers.openai.com/api/docs/guides/your-data.md
- openai 3.46.0 wheel from PyPI (`openai/resources/decisions.py`)

**Endpoint:** `POST https://api.openai.com/v1/decisions` (EU: `https://eu.api.openai.com/v1/decisions`). Auth `Authorization: Bearer $OPENAI_API_KEY`, `Content-Type: application/json`. The only supported model is `gpt-6-luna`. The page says answers are about 10x faster than the Responses API; no millisecond figure is given.

**Request fields:** `model` (required), `input` (required: string up to 10 MiB, or an ordered array of messages / function calls / tool outputs), `questions` (required, 1 to 400), optional `prompt_cache_key` (max 64 chars), `prompt_cache_options {mode: "implicit"|"explicit", ttl: "30m"}`, `safety_identifier` (max 128).

**Input messages:** `user` (parts `input_text`, `input_image`, `input_json`), `developer` and `system` (input text only; system is treated as developer), `assistant` (output text or refusal). `input_json` is `{"type":"input_json","data":{...}}`, user role only, limit 32 nesting levels, 10,000 values, 256 KiB compact. No audio, no files.

**Choice question:** `{"type":"choice","name":"meant","instructions":"...","choices":[{"value":"c1","description":"I'd like a coffee."},{"value":"none","description":"No candidate fits."}]}`. `choices` 2 to 255, unique; `value` is string or boolean (typed: `"true"` differs from `true`); `description` optional (up to 1 MiB). `instructions` is a string or an array of `input_text` / `input_image` / `input_json` parts.

**Request example (literal):**
```json
{
  "model": "gpt-6-luna",
  "input": [
    {"role": "developer", "content": [{"type": "input_text", "text": "Recogniser often swaps t, d and n, and k and g."}]},
    {"role": "user", "content": [
      {"type": "input_text", "text": "PHRASE BANK ...", "prompt_cache_breakpoint": {"mode": "explicit"}},
      {"type": "input_json", "data": {"recent_turns": ["..."], "candidates": [{"id": "c1", "text": "..."}]}}
    ]}
  ],
  "prompt_cache_options": {"mode": "explicit"},
  "questions": [{
    "type": "choice", "name": "meant",
    "instructions": "Which sentence did this speaker most likely say? Choose none if no candidate is likely.",
    "choices": [{"value": "c1", "description": "sentence 1"}, {"value": "none", "description": "no candidate"}]
  }]
}
```

**Response (from the docs, illustrative):**
```json
{"answers":[{"type":"choice","name":"meant","choice":"billing",
 "probabilities":[{"value":"billing","probability":0.95},{"value":"other","probability":0.02}],
 "confidence":0.93}],
 "model":"gpt-6-luna",
 "usage":{"input_tokens":0,"input_tokens_details":{"cached_tokens":0,"cache_write_tokens":0},"output_tokens":0,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":0}}
```
Answer `type` can also be `refusal` (only `name` and `type`), so check `answer.type` before reading `probabilities`. Python: `client.decisions.create(model=..., input=..., questions=[...])`, then `decision.answers[0]` with `.choice`, `.probabilities`, `.confidence`.

**Prompt caching:** implicit by default, one breakpoint at the end of shared `input`. The reusable prefix must be at least 1,024 tokens and identical across requests; question content is excluded from the prefix and the threshold. `prompt_cache_key` partitions reuse. Explicit mode: add `prompt_cache_breakpoint: {"mode":"explicit"}` to `input_text`/`input_image` parts and set `prompt_cache_options.mode="explicit"` (up to 4 breakpoints written; without breakpoints nothing is cached). TTL is `30m`, the only allowed value. Check `usage.input_tokens_details.cached_tokens` and `cache_write_tokens` (both already included in `input_tokens`).

**Pricing:** uncached input $0.10 per 1M tokens, output tokens free; cache reads are discounted, writes charged. Data-residency endpoints carry a 10% uplift.

**Data controls (your-data page):** `/v1/decisions` is Zero Data Retention eligible (eligible customers only), supports Private Retention with PSP, is HIPAA eligible, not used for training, 30-day abuse-monitoring retention otherwise. Regional storage: all listed regions; regional processing: United States and Europe (EEA + Switzerland); supported model `gpt-6-luna`. EU base URL `https://eu.api.openai.com/v1`, set `base_url` on the client. Region is chosen when creating a **new** project on an account with data residency enabled (contact sales). Not run: no key available.

**Limits/timeouts:** no rate-limit numbers published on these pages. `openai` Python defaults: 10 min read timeout, 2 retries; set `timeout=` per request (for example 3 s) and `max_retries=0` if you do your own retry.

**Gotchas:** the 1,024-token threshold means a short phrase bank will never cache; keep the static bank at least that long. Image limits are shared between `input` and question instructions (numbers not stated).

## 2. Anthropic Messages API (`claude-haiku-5-5`)

Sources:
- https://platform.claude.com/docs/en/about-claude/models/overview.md
- https://platform.claude.com/docs/en/models/haiku-5-5/overview.md
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs.md
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md
- https://platform.claude.com/docs/en/build-with-claude/effort.md and `adaptive-thinking.md`
- Context7 `/anthropics/anthropic-sdk-python` (`_constants.py`, `_client.py`)

**Model:** `claude-haiku-5-5` (alias and snapshot the same), fastest in the lineup, 1M context, 128K max output, from $0.10 / $0.50 per MTok in/out (prompts up to 100K tokens). Retirement not before 2027-10-07. Bedrock id `anthropic.claude-haiku-5-5`.

**Python SDK:** `anthropic` 2.6.0 (PyPI). `Anthropic(timeout=..., max_retries=...)`; per request `client.messages.create(..., timeout=1.2)`, and `client.with_options(timeout=1.2, max_retries=0)`. Defaults: timeout 600 s with 5 s connect, 2 retries on 408, 409, 429 and 5xx. `messages.create` accepts `timeout` but not `max_retries`.

**Structured output (GA):** request field `output_config.format`:
```json
{"model":"claude-haiku-5-5","max_tokens":512,
 "messages":[{"role":"user","content":"..."}],
 "output_config":{"format":{"type":"json_schema","schema":{
   "type":"object","properties":{"sentences":{"type":"array","items":{"type":"string"}}},
   "required":["sentences"],"additionalProperties":false}}}}
```
The JSON arrives as text in `content[0].text`. In Python, `client.messages.parse(..., output_format=PydanticModel)` returns `response.parsed_output`. Objects need `additionalProperties: false`; unsupported constraints (`minimum`, `minLength`, ...) are stripped and appended to the description by the SDK helper. Handle `stop_reason: "refusal"` and `"max_tokens"` (output may not match the schema). First use of a new schema adds grammar-compile latency; compiled grammars are cached 24 h from last use. Changing the schema or `output_config.format` invalidates the prompt cache.

**Prompt caching:** top-level `"cache_control": {"type":"ephemeral"}` (automatic: breakpoint on the last cacheable block) or `cache_control` on individual system/message blocks; add `"ttl":"1h"` for the 1-hour cache (default 5 minutes). **Minimum cacheable prompt for Haiku 5.5: 512 tokens**; shorter prompts are silently not cached. Check `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens`. Cache read price $0.01/MTok, 5-minute write $0.125/MTok (prompts up to 100K).

**Latency controls:** adaptive thinking is on by default at effort `medium`. Set `output_config.effort` to `low` (levels: low, medium, high, xhigh, max). `thinking: {"type":"disabled"}` is allowed at `high` or below (400 at xhigh/max). Telling the model "think less" in the prompt does not work reliably on Haiku 5.5. Changing effort between requests breaks the cache, so pick one setting. Stream with `client.messages.stream(...)` for progress.

**Auth:** `x-api-key: $ANTHROPIC_API_KEY`, `anthropic-version` header handled by the SDK.

## 3. ElevenLabs

Sources:
- https://elevenlabs.io/docs/api-reference/text-to-speech/stream.md
- https://elevenlabs.io/docs/api-reference/models/list.md
- https://elevenlabs.io/docs/api-reference/voices/search.md
- https://elevenlabs.io/docs/overview/models.md

**Stream endpoint:** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format=...`. Auth header `xi-api-key: $ELEVENLABS_API_KEY`. Response is a chunked audio byte stream. EU residency host: `https://api.eu.residency.elevenlabs.io`.

**Query:** `output_format` (default `mp3_44100_128`; also `mp3_22050_32`, `mp3_24000_48`, `mp3_44100_32/64/96/192`, `pcm_8000` to `pcm_48000`, `ulaw_8000`, `alaw_8000`, `opus_48000_*`). `ulaw_8000` is called out as the Twilio format. MP3 192 kbps needs Creator tier; PCM 44.1 kHz needs Pro. `enable_logging` (false means zero retention, enterprise only; also disables request stitching). `optimize_streaming_latency` is deprecated (0 to 4); prefer a Flash model.

**Body:** `text` (required), `model_id` (default `eleven_multilingual_v2`), `language_code`, `voice_settings`, `seed`, `previous_text`, `next_text`, `previous_request_ids`, `apply_text_normalization` (`auto|on|off`), `pronunciation_dictionary_locators` (up to 3).
`voice_settings`: `stability` (0.5), `similarity_boost` (0.75), `style` (0), `use_speaker_boost` (true), `speed` (1.0; below 1 slower), `clone_strength`.

```json
{"text":"I would like a coffee please.","model_id":"eleven_flash_v2_5",
 "voice_settings":{"stability":0.5,"similarity_boost":0.75,"speed":0.9}}
```

**Models:** `GET https://api.elevenlabs.io/v1/models` returns a list of `{model_id, name, can_do_text_to_speech, can_use_style, can_use_speaker_boost, token_cost_factor, maximum_text_length_per_request, languages:[{language_id,name}], model_rates:{character_cost_multiplier}, ...}`. Listed models include `eleven_v4`, `eleven_v4_turbo` (about 100 ms, 90+ languages), `eleven_v3`, `eleven_v3_conversational`, `eleven_multilingual_v2`, `eleven_flash_v2_5` (about 100 ms, 32 languages, 40,000 characters, 50% lower price per character), `eleven_flash_v2` (English). Flash v2.5 does not normalise numbers by default (enterprise can set `apply_text_normalization: "on"`); spell out phone numbers and times in the text.

**Voices:** `GET https://api.elevenlabs.io/v2/voices` with query `search`, `page_size` (max 100, default 10), `next_page_token`, `voice_type`, `category`, `include_total_count`, `voice_ids`. Response: `{voices:[{voice_id, name, category, labels:{...}, description, preview_url, settings, samples, ...}], has_more, total_count, next_page_token}`. `preview_url` is optional and nullable.

**Gotchas:** voices must exist in the account (premade or added); library voices on a free plan may be refused by the API (not verified here). Concurrency limits by plan are on the models overview page.

## 4. Twilio

Sources:
- https://www.twilio.com/docs/voice/media-streams/websocket-messages.md
- https://www.twilio.com/docs/voice/twiml/stream.md
- https://www.twilio.com/docs/voice/media-streams.md
- https://www.twilio.com/docs/voice/api/call-resource.md
- https://www.twilio.com/docs/usage/security.md

**Python lib:** `twilio` 9.13.0 (installed 9.10.9).

**Create call:** `POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Calls.json`, required `To` and `From` (E.164), plus `Url` (TwiML URL) or `Twiml` (inline; wins if both given). Others: `Method`, `StatusCallback`, `StatusCallbackEvent` (`initiated|ringing|answered|completed`), `Timeout` (default 60, max 600), `MachineDetection`, `Record`, `TimeLimit`.
```python
from twilio.rest import Client
client = Client(api_key, api_secret, account_sid)   # or Client(account_sid, auth_token)
call = client.calls.create(twiml=str(response), to="+15558675310", from_="+15552223214")
print(call.sid)
```

**TwiML (bidirectional):**
```python
from twilio.twiml.voice_response import Connect, VoiceResponse
r = VoiceResponse(); c = Connect()
s = c.stream(url="wss://host/twilio/media"); s.parameter(name="session", value="abc")
r.append(c); str(r)
```
Produces `<Response><Connect><Stream url="wss://host/twilio/media"><Parameter name="session" value="abc"/></Stream></Connect></Response>`. `url` must be `wss`, and cannot contain a query string. `<Parameter>` name plus value under 500 characters. With `<Connect><Stream>`, later TwiML runs only after your server closes the socket (or the `<Connect action>` URL is requested). Bidirectional streams receive only the `inbound` track. Regions IE1 and AU1 are supported for Media Streams.

**Messages from Twilio** (JSON text frames):
```json
{"event":"connected","protocol":"Call","version":"1.0.0"}
{"event":"start","sequenceNumber":"1","start":{"accountSid":"AC..","streamSid":"MZ..","callSid":"CA..","tracks":["inbound"],"mediaFormat":{"encoding":"audio/x-mulaw","sampleRate":8000,"channels":1},"customParameters":{"session":"abc"}},"streamSid":"MZ.."}
{"event":"media","sequenceNumber":"4","media":{"track":"inbound","chunk":"2","timestamp":"5","payload":"<base64 mulaw>"},"streamSid":"MZ.."}
{"event":"dtmf","streamSid":"MZ..","sequenceNumber":"5","dtmf":{"track":"inbound","digit":"1"}}
{"event":"mark","sequenceNumber":"4","streamSid":"MZ..","mark":{"name":"my label"}}
{"event":"stop","sequenceNumber":"5","stop":{"accountSid":"AC..","callSid":"CA.."},"streamSid":"MZ.."}
```
**Messages to Twilio:**
```json
{"event":"media","streamSid":"MZ..","media":{"payload":"<base64 mulaw 8k>"}}
{"event":"mark","streamSid":"MZ..","mark":{"name":"clip-17"}}
{"event":"clear","streamSid":"MZ.."}
```
Outbound payload must be raw `audio/x-mulaw`, 8000 Hz, base64, with no file header bytes (a WAV header garbles the stream); any chunk size is fine; media is buffered and played in order. Send a `mark` after a clip; Twilio echoes it when the clip has played. `clear` empties the buffer and Twilio echoes `mark`s for the dropped clips. The stream stops when the call ends or your server closes the socket.

**Request validation:** header `X-Twilio-Signature` is HMAC-SHA1 over the full URL plus sorted POST params, keyed with the Auth Token (API keys cannot validate). Python:
```python
from twilio.request_validator import RequestValidator
RequestValidator(auth_token).validate(url, params, signature)   # url = exact public URL Twilio called
```
Pass every received parameter. For JSON bodies the SDK uses `validate(url_with_query, body_string, signature)`. The Media Streams page says to validate `X-Twilio-Signature` for the stream connection as well; it does not spell out the URL form for the WebSocket handshake (not verified, validate against the exact `wss://` URL you put in TwiML, and test).

## 5. AI for Accessibility Toolkit

Sources:
- https://raw.githubusercontent.com/AI-for-Accessibility-Collective/AI-for-Accessibility-Toolkit/main/server/API.md
- .../main/toolkit/API.md
- .../main/toolkit/core/librarian.js, toolkit/surfaces/mobile.js, toolkit/platforms/chrome/web-surface.js, toolkit/registry/tools.js, server/src/profile-events.js
- local: `.claude/skills/ai4a11y-toolkit/SKILL.md`, `reference/http-api.md`, `reference/core-api.md`

**Reconciliation:** the local skill files are generated from the same source as `server/API.md` and `toolkit/API.md` and agree with them. The only addition from source is the argument and return detail below.

**Call shape:** `POST {TOOLKIT_URL}/v1/librarian/{method}`, header `Authorization: Bearer $TOOLKIT_TOKEN`, body `{"args":[...]}` (positional, same order as the in-process method; no body means `[]`). Success `200 {"ok":true,"result":...}`. Method threw: `200 {"ok":false,"error":"..."}` (check `ok`, it is not an HTTP error). Unknown method `404 {"error":"unknown-method"}`. Missing or bad token `401 {"error":"unauthorized"}`. `GET /v1/whoami` returns `{uid,label,kind}`. 51 routes; `server/API.md` lists arity but its `recordScopedSettings` shows 0 (introspection artefact; the real signature has three arguments).

**Arguments:**
- `getProfile` : `[]` -> the profile object (example in the skill: `{supportAreas:["vision"], fields:{needs:[{dimension:"textSize",value:1.5,strength:"preference"}], visionKind:"lowVision", readingLevel:6, largeTargets:true}}`).
- `getAbilityModel` : `[]` -> `{schemaVersion, supportAreas, freeText, language, readingLevel, confidence, needs[]}`.
- `effectivePreferences` (alias of `getEffectivePreferences`): `[url, contexts]`, `contexts` is an array like `["context:speech-translator"]`. Returns `{settings:{...}, applied:[...], provenance:{key:scope}, category, origin}`. Merge order, later wins: general, context, category, user profile, origin; `user-explicit` records are applied last and win (most specific scope first, then newest).
- `recordExplicitSetting` : `[key, value, origin]` -> record id array; writes to scope `general` (see Mismatch 10).
- `recordScopedSettings` : `[scope, settings, opts]` -> record id array. `scope` matches `^(general|category:[a-z-]+|context:[a-z-]+|origin:[a-z0-9.-]+|tool:[a-zA-Z0-9_-]+)$` (anything else falls back to `general`). `settings` is an object of key to value. `opts` optional `{writer:"person"|"agent"|"import", scopeLabel:"..."}`. One durable user-explicit record per key, updated in place.
- `hasScopedSetting` `[scope,key]`, `getScopedSetting` `[scope,key]` (value or undefined), `removeScopedSetting` `[scope,key]`.
- Also: `setProfileField [path,value]`, `setProfileFields [fields]`, `replaceProfile [profile, {id,name}?]`, `resetToProfile [opts]`, `logObservation [obs]`, `listProposals []`, `respondToProposal`, `addNote/listNotes/findNotes`.

**Preference vocabularies (source-verified):**
- *Needs* (`profile.fields.needs[]` = `{dimension, value, strength:"floor"|"preference"|"hint"}`): `textSize` (multiplier 1.0 to 2.0), `lineSpacing`, `letterSpacing`, `contrast` (bool or variant `light`, `yellow-black`), `darkTheme`, `reduceMotion`, `captions`, `simplify`, `readAloud`, `readAloudRate` (multiplier, 1.0 default), `describeImages`, `labelControls`, `keyboardAccess`. Profile fields also include `largeTargets` (bool), `readingLevel`, `visionKind` (`blind|lowVision|colorBlind`), `supportAreas` (`vision, hearing, motor, cognitive, reading, sensory`).
- *Mobile surface output* (`renderMobileSettings`): `{text:{scalePercent, lineSpacing, boldText}, display:{darkMode, highContrast, reduceTransparency}, motion:{reduceMotion}, media:{captions}, speech:{rate}, simplifyLanguage, touch:{largeTargets, minTargetPt}}`. `scalePercent = round(textSize*100)`; `largeTargets` is derived only from `supportAreas` containing `motor` (48 pt) else false (44 pt).
- *Web settings registry* (what `effectivePreferences().settings` and `recordScopedSettings` use): `fontScale` (50 to 200, percent), `lineHeight` (1.0 to 3.0), `letterSpacing` (0 to 0.5), `motionReducer` (bool), `darkMode`, `contrastMode` (`none|light|yellow-black`), `speechRate` (0.5 to 2.0), `readAloud`, `showCaptions`, `bigTargets`, `targetSize` (24 to 64 CSS px), `textSizeMethod` (`zoom|font`). Needs map to these via `deriveWebSettings` (`textSize*100 -> fontScale`, `reduceMotion -> motionReducer`, `contrast -> contrastMode`, `readAloudRate -> speechRate`, `captions -> showCaptions`). Unknown keys pass through unvalidated; known numeric keys are clamped to range.
- Suggested mapping: Text size = `fontScale` (percent) or need `textSize`; High contrast = `contrastMode != "none"` or need `contrast`; Motion off = `motionReducer` or need `reduceMotion`; Voice speed = `speechRate` or need `readAloudRate`; Larger buttons = `bigTargets` / profile field `largeTargets`; Captions = `showCaptions` or need `captions`. Read `getProfile` for needs and `effectivePreferences` for settings, then prefer a `user-explicit` setting over a derived need.

**Live updates:** `GET /v1/profile/events` with `Authorization: Bearer ...` (any token). Response `content-type: text/event-stream`. First frame on connect, then one per profile write, plus a `: ping` comment every 25 s:
```
retry: 3000
event: profile
id: 1790000000000
data: {"revision":1790000000000,"selected":{"id":"profile-3","name":"Profile 3","edited":false},"updatedAt":1790000000000}

```
`selected` is null for the default profile. The event carries no profile content; on every event call `getProfile` / `effectivePreferences` again. React Native `EventSource` cannot set headers; read the stream with `fetch` and a reader, or poll `GET /v1/profile/selection` (same object, plus `ok`). Other endpoints: `GET /v1/profile/presets`, `POST /v1/profile/select {id}`, `GET /v1/apps`, `POST /v1/mcp`.

**Server LLM lane:** `extract`, `reflect`, `buildSkill`, `interpretNeedsPrompt` use the service's Gemini key (`gemini-3.8-flash`); they throw `no-server-key` if the instance has none. The fast lane (profile, settings) does not.

## 6. TypeSafe AI "Jev"

Sources (TypeSafe's own, not OpenRouter):
- https://docs.typesafe.ai/llms.txt, `introduction/quickstart.md`, `primitives/choice.md`, `models.md`, `api/errors.md`, `api/list-models.md`, `api/system-one.md`, `sdk/python/api/constants.md`
- https://api.typesafe.ai/openapi.json (named by the docs), console https://console.typesafe.ai/keys
- OpenRouter's route, for comparison: https://openrouter.ai/blog/insights/what-is-jev/

**Answers to the coordinator's questions:** (a) the EU URL is OpenAI-specific, see section 1; TypeSafe documents no regional endpoint (ZDR is "for enterprise customers", see https://docs.typesafe.ai/legal.md). (b) TypeSafe's base URL is `https://api.typesafe.ai`; `jev-latest` is a valid model id (alias, currently `jev-1.14.0`); the endpoint does **not** mirror `/v1/decisions`.

**Base URL / auth:** `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer $TYPESAFE_API_KEY`, `Content-Type: application/json`. `GET https://api.typesafe.ai/v1/models` lists models (returned 403 `authentication_error` without a key, so it is live). Keys from https://console.typesafe.ai/keys.

**Models:** `jev-1.14.0` (from 2026-10-14; Choice, Score, Noul, Box; text and images), `jev-1.13.0` (no Box). Aliases: `jev-latest` and `jev-preview` both point to `jev-1.14.0` today. Context 64k per request and 32k per question (header `TypeSafe-Danger-Zone-Long-Context: true` raises both to 262k, slower and less accurate). Price $0.042 per 1M input tokens, output free. Each response `model` field gives the pinned id; use it to log which model answered. TypeSafe quotes 70 to 500 ms end to end on its landing material (third-party summary; not measured here).

**Request:**
```json
{"model":"jev-latest",
 "state":"<string, JSON object, or array of text values>",
 "questions":{
   "meant":{"type":"choice","instructions":"Which sentence did the speaker most likely say",
            "criteria":{"I'd like a coffee.":"candidate 1","None of these":"no candidate fits"}}}}
```
Question types: `choice` (`criteria` is a map option-name to description), `score` (`criteria` is an ordered array), `noul` (yes/no, `instructions` only), `box` (images, 1.14 only). `instructions` and each criterion may be a string, object or array. The model never sees the question id, but it does see option names and descriptions, so use the sentence itself (or a meaningful label) as the option key, not an opaque id like `c1`. A Choice supports up to 255 options (third-party summary).

**Response:**
```json
{"model":"jev-1.13.0",
 "answers":{"meant":{"type":"choice","choice":"technical","confidence":1.0,
                     "probabilities":{"technical":1.0,"billing":0.0}}},
 "usage":{"input_tokens":428,"output_tokens":73}}
```
`probabilities` is a map (OpenAI's is an array). Noul returns `{"type":"noul","noul":0.99}`. Score returns `score`, `legend`, `probabilities`, `confidence`.

**Limits and errors:** body at most 32 MiB; JSON nesting at most 64 levels; rate limits per organization in tokens/s and requests/s (console), `429` and `529 Overloaded` should be retried with backoff; `401` bad key, `422` malformed question, `400 max_tokens_exceeded` when over context. Per-request context includes `state` plus all questions, so the static phrase bank plus 8 candidates must stay well under 32k tokens.

**SDKs:** Python `typesafe-sdk` 0.7.5 (`from typesafe_sdk import Choice, TypeSafeClient`; `client.system_one(state=..., questions={...})`; reads `TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL`, `TYPESAFE_DEFAULT_MODEL`, `TYPESAFE_LOG_LEVEL`; Python 3.10+). npm `@typesafe-ai/sdk` 0.7.0. Plain `httpx` against `/v1/systemone` is enough.

**OpenRouter route (not what your env uses):** `POST https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.14` (pinned) or `~typesafe/jev-latest`; same TypeSafe request shape. Not OpenAI-compatible either.

**Not found:** no public `/v1/decisions`-style endpoint at TypeSafe, and no public latency SLA beyond the marketing range. Searches: web search for TypeSafe Jev API, then fetched typesafe.ai (Framer marketing site), docs.typesafe.ai (Mintlify, complete), api.typesafe.ai.

## 7. Modal (python 1.x; installed 1.5.1, latest 1.6.3)

Sources:
- https://modal.com/docs/examples/streaming_parakeet.md
- https://modal.com/docs/reference/modal.App.md, `modal.concurrent.md`, `modal.Volume.md`, `modal.Secret.md`, `modal.Image.md`, `modal.Function.md`, `modal.Cls.md`
- https://modal.com/docs/guide/gpu.md, `webhooks.md`, `volumes.md`, `images.md`, `scale.md`, `concurrent-inputs.md`, `trigger-deployed-functions.md`

**Class with GPU and one container** (pattern from the Parakeet example and the App reference):
```python
import modal
app = modal.App("speech-translator")
vol = modal.Volume.from_name("models", create_if_missing=True)
secrets = [modal.Secret.from_name("speech-keys")]          # or modal.Secret.from_dotenv(__file__)
image = (modal.Image.debian_slim(python_version="3.12")
         .uv_pip_install("torch", "transformers", "fastapi")
         .add_local_python_source("server"))

@app.cls(gpu="L4", image=image, volumes={"/cache": vol}, secrets=secrets,
         max_containers=1, min_containers=0, scaledown_window=900, timeout=3600)
@modal.concurrent(max_inputs=100)          # class level, not per method
class Serving:
    @modal.enter()
    def load(self): ...                    # runs once per container start
    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, WebSocket
        api = FastAPI()
        @api.websocket("/ws")
        async def ws(sock: WebSocket): await sock.accept(); ...
        return api
```
- `@app.cls(..., gpu, image, volumes, secrets, min_containers, max_containers, buffer_containers, scaledown_window, timeout=300 default, startup_timeout, region, enable_memory_snapshot, ...)`. `scaledown_window` is seconds an idle container lives; `min_containers=1` keeps one always on (use for `KEEP_WARM=1`; it can be changed at runtime with `Fn.autoscaler.update(min_containers=...)`).
- `@modal.concurrent(max_inputs=N, target_inputs=M)` replaces `allow_concurrent_inputs`; apply at class level for `@app.cls`. Sync methods must be thread-safe; async methods run as asyncio tasks. With `max_containers=1` plus `max_inputs` all connections land in one container.
- WebSockets work in `@modal.asgi_app`, `@modal.wsgi_app`, `@modal.web_server`: RFC 6455, one function call per connection, messages up to 2 MiB, no RFC 8441 or permessage-deflate. Use `@modal.concurrent` to hold many sockets in one container.
- GPU names in the guide: `T4, L4, A10, L40S, A100, A100-40GB, A100-80GB, RTX-PRO-6000, H100, H200, B200, B300`. Strings are validated server-side (not in the installed client), so I could not confirm that `"A10G"` is accepted; use `"A10"`.
- **Volumes:** `vol = modal.Volume.from_name("name", create_if_missing=True)`, mount with `volumes={"/cache": vol}`; inside a function `vol.commit()` persists writes, `vol.reload()` fetches writes from other containers.
- **Secrets:** `modal.Secret.from_name("name", required_keys=["KEY"])`, `modal.Secret.from_dotenv(path=None, filename=".env")`, `modal.Secret.from_dict({...})`; secrets arrive as environment variables.
- **Image:** `modal.Image.debian_slim(python_version=...)`, `.uv_pip_install(...)`, `.pip_install(...)`, `.apt_install(...)`, `.env({...})`, `.add_local_python_source("pkg", ignore=[...])`, `.add_local_dir(local, remote)`, `.run_function(fn, secrets=[...], volumes={...}, gpu=...)` to bake weights at build time (the guide's example downloads Hugging Face weights into a mounted volume or cache). Local files added last so edits rebuild fast.
- **Call another function:** `f = modal.Function.from_name("app", "fn"); f.remote(...)`, `f.spawn(...)`, `await f.spawn.aio(...)` (deployed apps only). For a class: `Model = modal.Cls.from_name("app", "Serving"); Model().method.remote(...)`; `Cls.with_options(gpu=...)` and `.with_concurrency(max_inputs=...)` override. Inside the same app call `Serving().method.remote.aio(...)` as the Parakeet example does. Methods exposed remotely need `@modal.method()`.
- **Web URL:** `modal deploy file.py` prints the URL for each web endpoint. Programmatically `modal.Function.from_name(...).get_web_url()` returns it, or `None` for non-web functions. Documented URL form is `https://<workspace>--<label>.modal.run` (examples `ecorp--web-demo-f-dev.modal.run`, `-dev` for `modal serve`); I did not find a documented rule for class methods, so read it from deploy output.
- **Parakeet streaming example:** `nvidia/parakeet-tdt-0.6b-v2` on `gpu="a10g"` (lowercase works in the example), `@modal.concurrent(max_inputs=14, target_inputs=10)`, `@modal.enter()` loads the model, a `@modal.method()` per audio chunk, a separate `WebServer` class with `@modal.asgi_app()` serving `/ws` that does `await ws.receive_bytes()` and `ws.send_text(...)`, silence detection with `pydub` so Parakeet is never fed silence, 16 kHz mono int16 chunks, an end-of-stream marker byte string, model weights cached in a Volume at `/cache` with `HF_HOME=/cache`. The server calls `model.handle_audio_chunk.remote.aio(chunk, audio_segment)`.

**Gotcha:** one `@modal.concurrent` container with sockets means anything shared in memory (Twilio stream and app session) must be keyed in a module-level dict inside the same container; `max_containers=1` guarantees it.

## 8. Expo

Sources:
- https://expo.dev/changelog/sdk-58.md
- https://raw.githubusercontent.com/expo/expo/sdk-58/packages/expo/bundledNativeModules.json
- https://docs.expo.dev/versions/v58.0.0/sdk/audio.md, `filesystem.md`, `speech.md`, `haptics.md`, `sqlite.md`, `async-storage.md`
- https://docs.expo.dev/router/advanced/tabs.md, `eas/json.md`, `build/internal-distribution.md`, `develop/development-builds/introduction.md`

**Versions:** `npm view expo` latest = 58.0.23 (SDK 58, released 2026-10-15; earlier lines 57, 56, 55 still tagged). SDK 58 bundles React Native **0.88.1** and React 19.3.0. Recommended: `expo-audio ~58.0.11`, `expo-file-system ~58.0.13`, `expo-speech ~58.0.3`, `expo-haptics ~58.0.7`, `expo-router ~58.0.30`, `expo-sqlite ~58.0.15`, `expo-dev-client ~58.0.18`, `@react-native-async-storage/async-storage 2.2.0`. Install with `npx expo install <pkg>`. SDK 58 targets iOS 27 (scene-based lifecycle); see the changelog if you edit AppDelegate.

**Router tabs:** `app/(tabs)/_layout.tsx` with `import { Tabs } from 'expo-router'`; `<Tabs screenOptions={{...}}><Tabs.Screen name="index" options={{title:"Home", tabBarIcon: ({color}) => ...}} /></Tabs>`. A `(tabs)` directory selects the Tabs layout. JS tabs ship with Expo Router since SDK 56. `NativeTabs` (system tab bar) also exists and is the recommended choice for iPhone Duo.

**Development build with EAS (works from Windows; iOS compiles in Expo's cloud):**
```json
{"build":{"development":{"developmentClient":true,"distribution":"internal",
  "android":{"buildType":"apk"},"ios":{"simulator":false}}}}
```
(The docs' own `development` profile sets `developmentClient: true`, Android `distribution: internal`; iOS `simulator: true` is for simulator builds only, so set it false for a device.) Install `expo-dev-client`. Commands: `eas device:create` (registers an iPhone for ad hoc provisioning via a URL/QR), `eas device:list`, `eas build --profile development --platform ios`. iOS ad hoc distribution needs a paid Apple Developer account and allows at most 100 iPhones a year; a newly registered device may not be installable until the first build includes it. Android internal builds need no Apple account.

**expo-audio playback:** `useAudioPlayer(source, options)` (auto-released on unmount) or `createAudioPlayer(source)` (you must `release()`); `player.play()`, `player.pause()`, `player.seekTo(0)`, `player.volume`, `player.replace(source)`; `useAudioPlayerStatus(player)` and the `playbackStatusUpdate` event give `didJustFinish`. `AudioSource` is a `require()` number, a string, or `{uri, headers, name}`; `uri` may be an HTTPS URL, a local file path, or a static resource name. **Data URIs are not documented**; write the MP3 bytes to a cache file and play that `file://` URI.
```ts
await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true,
  interruptionMode: 'duckOthers', shouldPlayInBackground: false, shouldRouteThroughEarpiece: false });
```
`AudioMode` fields: `playsInSilentMode` (default true), `allowsRecording` (iOS, default false), `allowsBackgroundRecording`, `shouldPlayInBackground`, `shouldRouteThroughEarpiece` (iOS earpiece routing only applies with `allowsRecording`), `interruptionMode` (`doNotMix | doNotMixPersistent | duckOthers | mixWithOthers`, default `mixWithOthers`), `interruptionModeAndroid` (deprecated). For capture plus playback keep `allowsRecording: true` so the session stays `playAndRecord`.

**expo-file-system (new API):** `import { File, Directory, Paths } from 'expo-file-system'`. `const f = new File(Paths.cache, 'clip.mp3'); f.create(); await f.write(uint8Array)` (accepts string, `ArrayBuffer`, `Uint8Array`; `FileWriteOptions {append, encoding: 'utf8'|'base64'}` so a base64 string can be written with `encoding: 'base64'`); `await f.base64()`, `f.uri`, `f.exists`, `f.delete()`. Legacy API: `import * as FileSystem from 'expo-file-system/legacy'`.

**expo-speech:** `Speech.speak(text, {language, rate, pitch, volume, voice, onDone, onStopped, useApplicationAudioSession})`, `Speech.stop()`, `await Speech.isSpeakingAsync()`, `await Speech.getAvailableVoicesAsync()` (voice `identifier` is device specific).

**expo-haptics:** `Haptics.selectionAsync()`, `Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light|Medium|Heavy|Rigid)`, `Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success|Warning|Error)`.

**Storage:** `expo-sqlite/kv-store` is a drop-in for AsyncStorage: `import Storage from 'expo-sqlite/kv-store'; await Storage.setItem(k, v); await Storage.getItem(k)`, plus sync `setItemSync/getItemSync`. `@react-native-async-storage/async-storage` 2.2.0 is also in the SDK bundle. Choose the kv-store (one fewer dependency).

## 9. @siteed/audio-studio v3

Sources:
- https://deeeed.github.io/audiolab/docs/api-reference/recording-config
- npm package `@siteed/audio-studio` 3.2.1 (README, `src/AudioStudio.types.ts`, `plugin/src/index.ts`, `package.json`), `@siteed/expo-audio-studio` 3.2.2 (shim)

**Package:** `@siteed/audio-studio` 3.2.1 (latest tag; `4.0.0-beta.0` on the beta tag). `@siteed/expo-audio-studio` 3.2.2 is deprecated and only re-exports it. Peer deps: `expo >= 52`, `react`, `react-native`, `@expo/config-plugins >= 7`. It is a native module, so it needs the development build.

**Hook:** `const { startRecording, stopRecording, pauseRecording, resumeRecording, prepareRecording, isRecording, isPaused, durationMs, size, analysisData } = useAudioRecorder();` (import `useAudioRecorder` from `@siteed/audio-studio`). `await startRecording(config)`; `await stopRecording()` returns `AudioRecording | null` (with `fileUri`). `prepareRecording(config)` pre-initialises the audio session and permissions (removes 50 to 300 ms of start latency). Permissions are requested by `startRecording`/`prepareRecording`.

**Config (`RecordingConfig`):** `sampleRate` (16000, 44100, 48000), `channels` (1|2), `encoding` (`pcm_8bit|pcm_16bit|pcm_32bit`; 8-bit is Android only), `interval` (ms, min 10), `intervalAnalysis`, `keepAwake` (continue in background, default true, needs iOS `audio` and `processing` modes), `showNotification`, `audioFocusStrategy`, `enableProcessing`, `streamFormat: 'raw' | 'float32'`, `output` (control files), `deviceId`, `autoResumeAfterInterruption`, `onAudioStream`, `onRecordingInterrupted`, `maxDurationMs`, `bufferDurationSeconds`. Defaults: Android 16 kHz/16-bit/mono; iOS 48 kHz/16-bit/mono; web 44.1 kHz/32-bit/mono. On iOS the library detects the hardware rate and resamples to your requested rate.

**Stream payload:** `onAudioStream: async (event: AudioDataEvent) => {...}` with `event = { data, position, fileUri, eventDataSize, totalSize, compression? }`. `data` is a **base64 string on native** (raw PCM bytes of the chosen encoding) and `Float32Array`/`Int16Array` on web when `streamFormat` is `'raw'`; with `streamFormat: 'float32'` it is a `Float32Array` in [-1, 1] on every platform (use `encoding: 'pcm_32bit'`). Byte order is not stated in the docs; the first design's plan (float32 in, convert to int16 little-endian) avoids the question.
```ts
await startRecording({ sampleRate: 16000, channels: 1, encoding: 'pcm_32bit',
  interval: 100, streamFormat: 'float32',
  onAudioStream: async (e) => { const f32 = e.data as Float32Array; /* to int16 LE, ws.send */ } });
```
At 100 ms and 16 kHz expect 1,600 samples per event (not verified on device).

**Config plugin (app.json):** `"plugins": [["@siteed/audio-studio", { "enableBackgroundAudio": true, "enableNotifications": false, "enablePhoneStateHandling": false, "enableDeviceDetection": true, "iosBackgroundModes": {"useAudio": true, "useProcessing": false, "useVoIP": false}, "iosConfig": {"microphoneUsageDescription": "..."} }]]`. Defaults: background audio, notifications, phone state and device detection all true; iOS modes all false. Android background adds a microphone foreground service. Turn off options you do not need to avoid extra permissions.

**Web:** supported (AudioWorklet, default 44.1 kHz 32-bit); the site must be HTTPS to use the mic. **Input device selection:** yes. `useAudioDevices()` returns `{devices, currentDevice, loading, error, selectDevice(id), resetToDefaultDevice, refreshDevices, initializeDeviceDetection}`, and `RecordingConfig.deviceId` picks one at start. **Stop:** `await stopRecording()`; `maxDurationMs` plus `autoStopOnMaxDuration` can stop for you.

## 10. Python libraries

Sources:
- silero-vad 6.2.3 wheel (`silero_vad/__init__.py`, `utils_vad.py`, `model.py`)
- transformers 5.22.2 wheel (`models/whisper/generation_whisper.py`, `english_normalizer.py`, `tokenization_whisper.py`, `generation/utils.py`), https://huggingface.co/docs/transformers/main/en/model_doc/whisper.md, https://huggingface.co/api/models/openai/whisper-large-v3-turbo
- Context7 `/huggingface/peft` (v0.21.2), peft docs `hotswap.md` via Context7
- jiwer 4.0.0 wheel; speechbrain 1.1.2 wheel, https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/raw/main/README.md

Latest on PyPI today: `silero-vad` 6.2.3, `transformers` 5.22.2 (installed 5.12.1), `peft` 0.21.2, `jiwer` 4.0.0, `speechbrain` 1.1.2, `torch` 2.15.0, `torchaudio` 2.11.1, `accelerate` 1.15.0.

**silero-vad:**
```python
from silero_vad import load_silero_vad, get_speech_timestamps, VADIterator
model = load_silero_vad()                      # onnx=False (JIT) by default; onnx=True needs onnxruntime
ts = get_speech_timestamps(wav_tensor, model, sampling_rate=16000, return_seconds=False)  # wav float32 mono tensor
vad = VADIterator(model, threshold=0.5, sampling_rate=16000, min_silence_duration_ms=100, speech_pad_ms=30)
for chunk in frames_512:                       # torch tensor, exactly 512 samples at 16 kHz (256 at 8 kHz)
    ev = vad(chunk, return_seconds=False)      # None, {'start': sample} or {'end': sample}
vad.reset_states()
```
Other exports: `read_audio`, `save_audio`, `collect_chunks`, `drop_chunks`, `get_speech_timestamps_from_probs`. `get_speech_timestamps` defaults: `threshold 0.5, min_speech_duration_ms 250, min_silence_duration_ms 100, speech_pad_ms 30, window_size_samples 512`. The VADIterator offset end is `temp_end + speech_pad - window`; it needs a chunk of exactly 512 samples or the model raises. `requires torch>=1.12`; the `audio`/`all` extras pin `torchaudio<2.10` (avoid).

**Whisper n-best (short-form, 30 s or less):**
```python
out = model.generate(input_features, num_beams=5, num_return_sequences=5, length_penalty=1.0,
                     return_dict_in_generate=True, output_scores=True, language="en", task="transcribe")
texts = processor.batch_decode(out.sequences, skip_special_tokens=True)   # batch*5 rows, best first
scores = out.sequences_scores                                              # shape (batch*5,)
```
`sequences_scores` is returned when `output_scores=True` (beam-search output `GenerateBeamEncoderDecoderOutput`). `length_penalty` default is 1.0 (higher promotes longer text; score is sum logprob divided by length^penalty). With `return_dict_in_generate=True` and no timestamps, Whisper returns the `ModelOutput` directly; for more than 3,000 mel frames (over 30 s) it switches to long-form, requires `return_timestamps=True`, and returns a dict instead. The checks `compression_ratio_threshold`, `logprob_threshold`, `no_speech_threshold` and temperature fallback are documented as long-form only (the fallback loop also runs for short-form internally, but `no_speech_threshold` needs `logprob_threshold` set, and fallback switches `num_beams` to 1 when sampling); compute the zlib compression ratio and avg logprob yourself on the n-best. Large-v3-turbo is `openai/whisper-large-v3-turbo` (files include `normalizer.json`). Not run: no GPU or weights here.

**peft LoRA swap:**
```python
from peft import PeftModel
model = PeftModel.from_pretrained(base_model, "path/user", adapter_name="user")  # first adapter
model.load_adapter("path/other", adapter_name="other")      # loads but does not activate
model.set_adapter("other")                                   # activate one
model.delete_adapter("other")                                # free it
base = model.unload()                                        # strip LoRA layers, returns base (assign it)
with model.disable_adapter(): model.generate(...)            # base model output, no unload
```
Several at once: `model.base_model.set_adapter(["a","b"])`. In-place weight replacement, preferred for speed and for `torch.compile`: `from peft.utils.hotswap import hotswap_adapter; hotswap_adapter(model, path, adapter_name="user", torch_device=device)` (LoRA only; new adapter must target the same or a subset of layers; call `prepare_model_for_compiled_hotswap(model, target_rank=max_rank)` first if ranks differ). `hotswap_adapter_from_state_dict(model, state_dict, adapter_name, torch_device)` takes an in-memory dict.

**jiwer 4.0.0:**
```python
import jiwer
jiwer.wer(reference, hypothesis)                  # float; str or list[str] for both
o = jiwer.process_words(reference, hypothesis)    # o.wer, o.mer, o.wil, o.wip, o.hits, o.substitutions, o.deletions, o.insertions, o.alignments
jiwer.cer(reference, hypothesis)
```
Both accept `reference_transform` and `hypothesis_transform` (default `wer_default`).

**Whisper English normaliser:**
```python
from transformers.models.whisper.english_normalizer import EnglishTextNormalizer
import json
from huggingface_hub import hf_hub_download
spelling = json.load(open(hf_hub_download("openai/whisper-large-v3-turbo", "normalizer.json")))
norm = EnglishTextNormalizer(spelling)          # constructor needs the british-to-american mapping dict
norm("It's Mr. Smith's colour")
```
Equivalent: `processor.tokenizer.normalize(text)` (uses `tokenizer.english_spelling_normalizer`, loaded from `normalizer.json`). `BasicTextNormalizer(remove_diacritics=False, split_letters=False)` lives in the same module for non-English. Note the English normaliser converts British to American spelling, so use it on both reference and hypothesis for WER, never on text shown to the user.

**speechbrain ECAPA:**
```python
from speechbrain.inference.speaker import EncoderClassifier       # defined in speechbrain.inference.classifiers
clf = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir="pretrained_models/ecapa", run_opts={"device":"cuda"})
emb = clf.encode_batch(wav)        # wav: float tensor [batch, time] at 16 kHz; returns an embedding tensor; optional wav_lens, normalize=False
```
Input must already be 16 kHz mono (only `classify_file` resamples). I did not fetch the embedding size or output shape; print `emb.shape` once.

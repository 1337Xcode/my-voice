"""Live: the streamed voice against ElevenLabs (run with `uv run pytest -m live`)."""

import asyncio
import os

import pytest

from voice.realtime.voice_stream import VoiceStream

pytestmark = pytest.mark.live


@pytest.mark.parametrize("fmt", ["pcm_24000", "ulaw_8000"])
def test_three_sentences_on_one_connection_each_end_with_a_final_chunk(fmt):
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or os.environ.get("ELEVENLABS_DEFAULT_VOICE_ID")
    if not os.environ.get("ELEVENLABS_API_KEY") or not voice_id:
        pytest.skip("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are needed")

    async def run():
        stream = VoiceStream(voice_id, fmt, 1.0)
        results = []
        for sentence in ("Could I have a glass of water, please?", "Thank you, that is very kind.", "See you tomorrow."):
            chunks = []

            async def on_chunk(audio, seq, final):
                chunks.append((len(audio), seq, final))

            results.append((await stream.speak(sentence, on_chunk), chunks))
        await stream.close()
        return results

    for result, chunks in asyncio.run(run()):
        assert result.audio_bytes > 4000
        assert chunks[-1][2] is True and all(not final for _, _, final in chunks[:-1])
        assert result.first_chunk_ms < 1500

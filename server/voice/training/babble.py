"""The babble bank (spec 9.4) and mixing speech with babble at a set SNR, for training and the synthetic test sets."""

import tarfile
import zlib
from pathlib import Path

import numpy as np

from voice.audio.pcm import SAMPLE_RATE, read_audio, write_wav
from voice.clips.selection import BABBLE_SNR_DB, FrozenTestSet, condition_audio
from voice.storage import shared_dir, write_json

LIBRISPEECH_URL = "https://www.openslr.org/resources/12/dev-clean.tar.gz"
TRACKS = 20
TRACK_S = 30.0
SPEAKERS_PER_TRACK = 6
BANK_SEED = 94
TRACK_LUFS = -23.0
DOWNLOAD_TIMEOUT_S = 60
# Never let a mix clip: scale the whole mix down if its peak passes this.
MAX_PEAK = 0.99


def babble_dir() -> Path:
    """Where the bank's tracks live on the speech-data volume."""
    return shared_dir("noise", "babble")


def download_librispeech(workdir: Path) -> Path:
    """Downloads and unpacks LibriSpeech dev-clean; returns the folder of speaker folders."""
    import httpx

    archive = workdir / "dev-clean.tar.gz"
    with httpx.stream("GET", LIBRISPEECH_URL, timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True) as response:
        response.raise_for_status()
        with archive.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    with tarfile.open(archive) as tar:
        tar.extractall(workdir, filter="data")
    return workdir / "LibriSpeech" / "dev-clean"


def normalise_loudness(audio: np.ndarray, target_lufs: float) -> np.ndarray:
    """Scales audio to an integrated loudness (ITU-R BS.1770) in LUFS."""
    import pyloudnorm

    loudness = pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(audio)
    return (audio * 10 ** ((target_lufs - loudness) / 20)).astype(np.float32)


def speaker_stream(utterances: list[Path], rng: np.random.Generator) -> np.ndarray:
    """30 s of one speaker: their utterances in random order, joined, from a random start, at a fixed loudness."""
    length = int(TRACK_S * SAMPLE_RATE)
    pieces, total = [], 0
    for index in rng.permutation(len(utterances)):
        pieces.append(read_audio(utterances[index]))
        total += len(pieces[-1])
        if total >= 2 * length:
            break
    joined = np.tile(np.concatenate(pieces), 2)
    start = int(rng.integers(0, len(joined) - length))
    return normalise_loudness(joined[start : start + length], TRACK_LUFS)


def build_babble_bank(librispeech: Path) -> dict:
    """Writes 20 tracks of 30 s, each 6 random LibriSpeech speakers mixed and loudness-normalised."""
    speakers = {folder.name: sorted(folder.rglob("*.flac")) for folder in sorted(librispeech.iterdir()) if folder.is_dir()}
    rng = np.random.default_rng(BANK_SEED)
    tracks = []
    for number in range(1, TRACKS + 1):
        chosen = sorted(rng.choice(sorted(speakers), size=SPEAKERS_PER_TRACK, replace=False).tolist())
        mix = normalise_loudness(sum(speaker_stream(speakers[name], rng) for name in chosen), TRACK_LUFS)
        mix = mix * min(1.0, MAX_PEAK / float(np.max(np.abs(mix))))
        write_wav(babble_dir() / f"babble_{number:02d}.wav", mix)
        tracks.append({"file": f"babble_{number:02d}.wav", "librispeech_speakers": chosen})
    manifest = {"source": LIBRISPEECH_URL, "licence": "CC BY 4.0", "seconds": TRACK_S, "lufs": TRACK_LUFS, "tracks": tracks}
    write_json(babble_dir() / "bank.json", manifest)
    return manifest


def load_babble_bank() -> list[np.ndarray]:
    """Every babble track, or an error naming the command that builds them."""
    paths = sorted(babble_dir().glob("babble_*.wav"))
    if not paths:
        raise FileNotFoundError(f"No babble bank in {babble_dir()}; run build_noise_bank first.")
    return [read_audio(path) for path in paths]


def babble_segment(bank: list[np.ndarray], length: int, rng: np.random.Generator) -> np.ndarray:
    """A random stretch of a random track, `length` samples long (wrapping round the track)."""
    track = bank[int(rng.integers(len(bank)))]
    start = int(rng.integers(len(track)))
    return np.resize(np.roll(track, -start), length)


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Speech plus noise scaled so speech power over noise power is `snr_db`; never clips."""
    speech_power = float(np.mean(speech**2))
    noise_power = float(np.mean(noise**2))
    if speech_power == 0.0 or noise_power == 0.0:
        return speech.astype(np.float32)
    scale = np.sqrt(speech_power / (noise_power * 10 ** (snr_db / 10)))
    mixed = speech + scale * noise[: len(speech)]
    peak = float(np.max(np.abs(mixed)))
    return (mixed * (MAX_PEAK / peak if peak > MAX_PEAK else 1.0)).astype(np.float32)


def make_babble_tests(speaker: str, frozen: FrozenTestSet) -> int:
    """Writes the babble_5db and babble_0db test audio; each clip's mix has its own fixed seed. Returns the count."""
    bank = load_babble_bank()
    written = 0
    for condition, snr_db in BABBLE_SNR_DB.items():
        for clip_id in frozen.conditions[condition]:
            speech = read_audio(condition_audio(speaker, "quiet", clip_id))
            # A per-clip seed keeps every existing mix identical when new test clips join the set.
            rng = np.random.default_rng(zlib.crc32(f"{clip_id}|{condition}".encode()))
            write_wav(condition_audio(speaker, condition, clip_id), mix_at_snr(speech, babble_segment(bank, len(speech), rng), snr_db))
            written += 1
    return written

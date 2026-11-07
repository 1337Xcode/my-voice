"""Fine-tune and score Whisper on one speaker's speech, on Modal.

Run from this folder, pointing --data-dir at the local copy of hack-speech/
(the folder with clips.csv, raw/, practice/):

  modal run app.py::upload     --data-dir ../hack-speech
  modal run app.py::baseline   --speaker P1 --data-dir ../hack-speech
  modal run app.py::train      --speaker P1 --name p1-test --epochs 2
  modal run app.py::evaluate   --speaker P1 --model p1-test --data-dir ../hack-speech
  modal run app.py::score      --speaker P1 --data-dir ../hack-speech
  modal run app.py::transcribe --model p1-test --file some.wav

Audio conversion (ffmpeg) runs on Modal, so the laptop only needs `pip install modal`.
"""

import csv
import io
import json
import time
from datetime import datetime
from pathlib import Path

import modal
import checks
from checks import (PIPELINE_VERSION, DECODING, digest, file_hash, sentence_key,
                    check_duration, prepare_manifest, fixed_validation,
                    unique_candidates, verify_result, evaluation_record)

CODE_SHA256 = digest([Path(__file__).read_text(), Path(checks.__file__).read_text()])

BASE_MODEL = "openai/whisper-large-v3-turbo"
GPU = "A10G"

app = modal.App("speech-whisper")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.5.1",
        "transformers==4.46.3",
        "peft==0.13.2",
        "jiwer==3.0.5",
        "soundfile==0.12.1",
        "numpy<2.2",
    )
    .env({"HF_HOME": "/models/_hf_cache"})  # cache base weights on the volume
    .add_local_python_source("checks")  # Modal requires add_local_* to be the last step
)

data_vol = modal.Volume.from_name("speech-data", create_if_missing=True)
models_vol = modal.Volume.from_name("speech-models", create_if_missing=True)
VOLS = {"/data": data_vol, "/models": models_vol}

CSV_COLS = ["id", "speaker", "text", "file", "split", "condition", "ok", "notes"]
SCORE_COLS = ["system", "speaker", "condition", "wer", "n_clips", "notes"]


# ---------- plain helpers (also used locally) ----------

def read_clips(csv_text, speaker=None):
    """Rows with ok == yes (optionally one speaker). Friendly errors on bad files."""
    reader = csv.DictReader(io.StringIO(csv_text))
    missing = [c for c in CSV_COLS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(f"clips.csv is missing columns: {missing}")
    rows = []
    seen = set()
    for r in reader:
        # keep only the contract columns so local and uploaded CSV hash the same
        r = {k: (r.get(k) or "").strip() for k in CSV_COLS}
        if r["ok"].lower() != "yes":
            continue
        if speaker and r["speaker"] != speaker:
            continue
        if r["split"] not in ("train", "test"):
            raise SystemExit(f"row {r['id']}: split must be train or test, got '{r['split']}'")
        if not r['text'] or r['condition'] not in ('quiet', 'noisy'):
            raise ValueError(f"{r['id']}: empty text or invalid condition")
        if (r['speaker'], r['id']) in seen:
            raise ValueError(f"duplicate clip id: {r['id']}")
        seen.add((r['speaker'], r['id']))
        rows.append(r)
    if speaker and not rows:
        raise SystemExit(f"no rows with ok=yes for speaker {speaker}")
    return rows


def split_rows(rows, normalize=sentence_key):
    """Train/test split with a hard leak check on ids AND sentence text."""
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    test_ids = {r["id"] for r in test}
    test_texts = {normalize(r["text"]) for r in test}
    leaked_ids = [r["id"] for r in train if r["id"] in test_ids]
    leaked_txt = [r["id"] for r in train if normalize(r["text"]) in test_texts]
    print(f"train clips: {len(train)}  test clips: {len(test)}  "
          f"id overlap: {len(leaked_ids)}  text overlap: {len(leaked_txt)}")
    if leaked_ids or leaked_txt:
        raise ValueError(f"test/train overlap: ids={leaked_ids}, sentences={leaked_txt}")
    return train, test


def write_csv(path, rows, cols):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}")


# ---------- remote: audio + model helpers ----------

def _load_wav(path):
    import soundfile as sf
    audio, sr = sf.read(path, dtype="float32")
    assert sr == 16000, f"{path} is {sr} Hz, expected 16000"
    if getattr(audio, 'ndim', 1) != 1:
        raise ValueError(f"{path}: audio must be mono")
    check_duration(len(audio), sr, str(path))
    return audio


def _to_wav(src, dst):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                    "-ac", "1", "-ar", "16000", dst], check=True)


def _load_model(adapter=None):
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    processor = WhisperProcessor.from_pretrained(BASE_MODEL)
    model = WhisperForConditionalGeneration.from_pretrained(
        BASE_MODEL, torch_dtype=torch.float16, attn_implementation="sdpa")
    if adapter:
        from peft import PeftModel
        path = f"/models/{adapter}"
        if not Path(path).exists():
            raise SystemExit(f"no model '{adapter}' on volume speech-models")
        model = PeftModel.from_pretrained(model, path).merge_and_unload()
    return processor, model.to("cuda").eval()


def _transcribe(processor, model, audios, nbest=1, beams=5):
    """Returns a list of n-best lists (best first, distinct texts, up to nbest)."""
    import torch
    out = []
    torch.manual_seed(DECODING["seed"])
    for audio in audios:
        check_duration(len(audio))
        feats = processor.feature_extractor(
            audio, sampling_rate=16000, return_tensors="pt").input_features
        feats = feats.to("cuda", torch.float16)
        common = dict(language="en", task="transcribe", max_new_tokens=128)
        with torch.no_grad():
            # top-1: plain beam search (this is what WER is scored on)
            texts = processor.batch_decode(
                model.generate(feats, num_beams=beams, **common), skip_special_tokens=True)
            if nbest > 1:
                # alternatives: plain beams are near-duplicates for Whisper and
                # diverse beam search loops, so sample a few and drop runaway ones
                n_words = len(texts[0].split())
                alt = model.generate(feats, do_sample=True, temperature=0.7, top_k=50,
                                     num_return_sequences=nbest * 2,
                                     language="en", task="transcribe",
                                     max_new_tokens=int(n_words * 3 + 10))
                texts += [t for t in processor.batch_decode(alt, skip_special_tokens=True)
                          if len(t.split()) <= n_words * 1.5 + 2]
        out.append(unique_candidates(texts, nbest))
    return out


# ---------- remote functions ----------

def _verified_rows(speaker):
    data_vol.reload()
    folder = Path(f"/data/{speaker}")
    rows = read_clips((folder / "clips.csv").read_text(), speaker)
    manifest = json.loads((folder / "manifest.json").read_text())
    ready = json.loads((folder / "ready.json").read_text())
    if digest(rows) != manifest['rows_sha256'] or ready['dataset_sha256'] != manifest['dataset_sha256']:
        raise ValueError('Upload/conversion is incomplete. Run upload again.')
    for r in rows:
        entry = ready['entries'][r['id']]
        path = folder / entry['wav']
        if not path.is_file() or file_hash(path) != entry['sha256']:
            raise ValueError(f"{r['id']}: converted WAV missing/changed; upload again")
        r['_wav'] = str(path)
    return rows, manifest


def _partitions(speaker, rows):
    split_rows(rows)
    train, val = fixed_validation(rows, Path(f"/data/{speaker}/validation_split.json"))
    data_vol.commit()
    return train, val, [r for r in rows if r['split'] == 'test']


def _evaluation_metadata(manifest, split):
    return {'pipeline_version': PIPELINE_VERSION, 'evaluation_code_sha256': CODE_SHA256,
            'dataset_sha256': manifest['dataset_sha256'],
            'evaluation_dataset_sha256': manifest['dataset_sha256'], 'eval_split': split,
            'decoding': DECODING, 'evaluated_at': datetime.now().isoformat(timespec='seconds')}


@app.function(image=image, volumes=VOLS, timeout=1800)
def convert(speaker: str):
    data_vol.reload()
    folder = Path(f"/data/{speaker}")
    rows = read_clips((folder / 'clips.csv').read_text(), speaker)
    manifest = json.loads((folder / 'manifest.json').read_text())
    if digest(rows) != manifest['rows_sha256']:
        raise ValueError('CSV does not match uploaded manifest')
    (folder / 'wav').mkdir(exist_ok=True)
    entries = {}
    for r in rows:
        e = manifest['entries'][r['id']]
        src = folder / e['source']
        if not src.is_file() or file_hash(src) != e['sha256']:
            raise ValueError(f"{r['id']}: exact source missing/changed; upload again")
        rel = f"wav/{r['id']}-{e['sha256']}.wav"
        _to_wav(str(src), str(folder / rel))
        _load_wav(folder / rel)  # validates duration before publishing a ready manifest
        entries[r['id']] = {'wav': rel, 'sha256': file_hash(folder / rel)}
    (folder / 'ready.json').write_text(json.dumps({
        'dataset_sha256': manifest['dataset_sha256'], 'entries': entries}, indent=2))
    data_vol.commit()
    print(f"{speaker}: verified and converted {len(rows)} clips")
    return len(rows)


@app.function(image=image, volumes=VOLS, gpu=GPU, timeout=3600)
def run_baseline(speaker: str, split: str = 'validation'):
    rows, manifest = _verified_rows(speaker)
    _, val, test = _partitions(speaker, rows)
    test = val if split == 'validation' else test
    if not test:
        raise ValueError(f'No {split} clips')
    processor, model = _load_model()
    models_vol.commit()  # keep the downloaded base weights
    hyps = _transcribe(processor, model, [_load_wav(r["_wav"]) for r in test])
    return [{"id": r["id"], "condition": r["condition"], "reference": r["text"],
             "hypothesis": h[0]} for r, h in zip(test, hyps)], _evaluation_metadata(manifest, split)


@app.function(image=image, volumes=VOLS, gpu=GPU, timeout=7200)
def run_train(speaker: str, name: str, epochs: int, lr: float, rank: int,
              batch: int, accum: int, seed: int):
    import random
    import shutil

    import jiwer
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (WhisperForConditionalGeneration, WhisperProcessor,
                              get_linear_schedule_with_warmup)

    if min(epochs, rank, batch, accum) <= 0 or lr <= 0:
        raise ValueError('epochs, rank, batch, accum and lr must be positive')
    out = Path(f"/models/{name}")
    if out.exists():
        raise ValueError(f'Model {name} already exists; use a new name.')
    torch.manual_seed(seed)
    random.seed(seed)
    processor = WhisperProcessor.from_pretrained(BASE_MODEL)
    norm = processor.tokenizer.normalize
    rows, manifest = _verified_rows(speaker)
    split_rows(rows, normalize=norm)
    train, val, _ = _partitions(speaker, rows)
    if {norm(r['text']) for r in train} & {norm(r['text']) for r in val}:
        raise ValueError('Normalised sentences overlap training and validation; standardise transcripts and create a new split.')
    print(f"training on {len(train)}, validating on {len(val)}")
    if len(train) < 5:
        raise SystemExit("fewer than 5 training clips: record more before training")

    tok = processor.tokenizer
    tok.set_prefix_tokens(language="en", task="transcribe", predict_timestamps=False)

    def featurize(r):
        audio = _load_wav(r["_wav"])
        feats = processor.feature_extractor(audio, sampling_rate=16000,
                                            return_tensors="pt").input_features[0]
        labels = tok(r["text"]).input_ids
        return feats, labels

    train_items = [featurize(r) for r in train]
    val_items = [featurize(r) for r in val]

    model = WhisperForConditionalGeneration.from_pretrained(
        BASE_MODEL, torch_dtype=torch.float32, attn_implementation="sdpa")
    models_vol.commit()
    start_id = model.config.decoder_start_token_id
    # light SpecAugment (applied by the model only in training mode)
    model.config.apply_spec_augment = True
    model.config.mask_time_prob = 0.05
    model.config.mask_feature_prob = 0.0
    model = get_peft_model(model, LoraConfig(
        r=rank, lora_alpha=rank * 2, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "out_proj"]))  # encoder + decoder
    model.print_trainable_parameters()
    model.to("cuda")

    def collate(items):
        feats = torch.stack([f for f, _ in items])
        labs = [l[1:] if l[0] == start_id else l for _, l in items]  # model adds start token
        width = max(len(l) for l in labs)
        labels = torch.full((len(labs), width), -100, dtype=torch.long)
        for i, l in enumerate(labs):
            labels[i, : len(l)] = torch.tensor(l)
        return feats.to("cuda"), labels.to("cuda")

    def loss_on(items):
        model.eval()
        total = 0.0
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
            for i in range(0, len(items), batch):
                f, l = collate(items[i:i + batch])
                total += model(input_features=f, labels=l).loss.item() * len(f)
        return total / len(items)

    def val_wer():
        model.eval()
        inner = model.get_base_model()
        refs, hyps = [], []
        for (f, _), r in zip(val_items, val):
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                ids = inner.generate(f[None].to("cuda"), language="en",
                                     task="transcribe", num_beams=5, max_new_tokens=128)
            refs.append(norm(r["text"]))
            hyps.append(norm(processor.batch_decode(ids, skip_special_tokens=True)[0]))
        return jiwer.wer(refs, hyps)

    steps_per_epoch = max(1, -(-len(train_items) // (batch * accum)))
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    sched = get_linear_schedule_with_warmup(
        opt, int(0.1 * steps_per_epoch * epochs), steps_per_epoch * epochs)

    out = Path(f"/models/{name}")
    if out.exists():
        raise ValueError(f'Model {name} already exists; use a new name to preserve the previous run.')
    best = (float("inf"), -1)
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        random.shuffle(train_items)
        running, n = 0.0, 0
        for step, i in enumerate(range(0, len(train_items), batch)):
            f, l = collate(train_items[i:i + batch])
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(input_features=f, labels=l).loss
            (loss / accum).backward()
            running += loss.item() * len(f)
            n += len(f)
            if (step + 1) % accum == 0 or i + batch >= len(train_items):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
        tr_loss, v_loss, v_wer = running / n, loss_on(val_items), val_wer()
        history.append({"epoch": epoch, "train_loss": tr_loss, "val_loss": v_loss, "val_wer": v_wer})
        flag = ""
        if v_wer < best[0] or (v_wer == best[0] and v_loss < history[best[1] - 1]["val_loss"]):
            best = (v_wer, epoch)
            if out.exists():
                shutil.rmtree(out)
            model.save_pretrained(out)
            processor.save_pretrained(out)
            flag = "  <- best, saved"
        print(f"epoch {epoch}: train loss {tr_loss:.3f}  val loss {v_loss:.3f}  val WER {v_wer:.3f}{flag}")

    config = {"speaker": speaker, "base": BASE_MODEL, "epochs": epochs, "lr": lr, "rank": rank,
              "batch": batch, "accum": accum, "seed": seed, "n_train": len(train),
              "n_val": len(val), "best_epoch": best[1], "best_val_wer": best[0],
              "train_ids": sorted(r["id"] for r in train), "val_ids": sorted(r["id"] for r in val),
              "train_texts": sorted(norm(r['text']) for r in train),
              "val_texts": sorted(norm(r['text']) for r in val),
              "pipeline_version": PIPELINE_VERSION, "training_code_sha256": CODE_SHA256,
              "dataset_sha256": manifest['dataset_sha256'],
              "training_dataset_sha256": manifest['dataset_sha256'],
              "validation_sha256": digest([(r['id'], r['text'], file_hash(r['_wav'])) for r in val]),
              "history": history, "trained_at": datetime.now().isoformat(timespec="seconds")}
    (out / "train_config.json").write_text(json.dumps(config, indent=2))
    models_vol.commit()
    print(f"saved {name} (best epoch {best[1]}, val WER {best[0]:.3f}) to volume speech-models")
    return config


@app.function(image=image, volumes=VOLS, gpu=GPU, timeout=3600)
def run_evaluate(speaker: str, adapter: str, split: str = 'validation'):
    rows, manifest = _verified_rows(speaker)
    _, val, test = _partitions(speaker, rows)
    cfg_path = Path(f"/models/{adapter}/train_config.json")
    cfg = json.loads(cfg_path.read_text())
    if cfg.get('pipeline_version') != PIPELINE_VERSION or cfg.get('speaker') != speaker:
        raise ValueError('Legacy or wrong-speaker adapter: retrain with this pipeline under a new name.')
    processor, model = _load_model(adapter)
    norm = processor.tokenizer.normalize
    selected = val if split == 'validation' else test
    if not selected:
        raise ValueError(f'No {split} clips')
    if split == 'validation' and digest([(r['id'], r['text'], file_hash(r['_wav'])) for r in val]) != cfg['validation_sha256']:
        raise ValueError('Validation data changed since training; do not compare these scores.')
    used_ids = set(cfg['train_ids']) | (set(cfg['val_ids']) if split == 'test' else set())
    used_texts = set(cfg['train_texts']) | (set(cfg['val_texts']) if split == 'test' else set())
    if used_ids & {r['id'] for r in selected} or used_texts & {norm(r['text']) for r in selected}:
        raise ValueError('Evaluation clips overlap training/model-selection data')
    test = selected
    hyps = _transcribe(processor, model,
                       [_load_wav(r["_wav"]) for r in test], nbest=5)
    rows_out = [{"id": r["id"], "condition": r["condition"], "reference": r["text"],
                 "hypothesis": h[0], "nbest": " | ".join(h)} for r, h in zip(test, hyps)]
    return rows_out, evaluation_record(cfg, _evaluation_metadata(manifest, split))


@app.function(image=image, volumes=VOLS, timeout=600)
def normalize_texts(texts: list):
    from transformers import WhisperTokenizer
    tok = WhisperTokenizer.from_pretrained(BASE_MODEL)
    return [tok.normalize(t or "") for t in texts]


@app.cls(image=image, volumes=VOLS, gpu=GPU, timeout=1200)
class Transcriber:
    adapter: str = modal.parameter()

    @modal.enter()
    def load(self):
        self.processor, self.model = _load_model(self.adapter or None)

    @modal.method()
    def run(self, audio_bytes: bytes, suffix: str):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src, dst = f"{d}/in{suffix}", f"{d}/in.wav"
            Path(src).write_bytes(audio_bytes)
            _to_wav(src, dst)
            audio = _load_wav(dst)
        t0 = time.perf_counter()
        nbest = _transcribe(self.processor, self.model, [audio], nbest=5)[0]
        return nbest, round((time.perf_counter() - t0) * 1000)


# ---------- local entrypoints ----------

def _clips_path(data_dir):
    p = Path(data_dir).expanduser() / "clips.csv"
    if not p.exists():
        raise SystemExit(f"can't find {p}")
    return p


def _results(data_dir):
    return Path(data_dir).expanduser() / "results"


@app.local_entrypoint()
def upload(data_dir: str = "../hack-speech"):
    root = Path(data_dir).expanduser()
    rows = read_clips(_clips_path(data_dir).read_text())
    if not rows:
        raise SystemExit("no rows with ok=yes in clips.csv")
    speakers = sorted({r["speaker"] for r in rows})
    # Validate every file before any upload; content-addressed paths prevent stale reuse.
    manifests = {sp: prepare_manifest(root, [r for r in rows if r['speaker'] == sp]) for sp in speakers}
    with data_vol.batch_upload(force=True) as batch:
        for sp in speakers:
            sp_rows = [r for r in rows if r['speaker'] == sp]
            manifest = manifests[sp]
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=CSV_COLS, extrasaction='ignore')
            w.writeheader()
            w.writerows(sp_rows)
            for r in sp_rows:
                batch.put_file(str(root / r['file']), f"/{sp}/{manifest['entries'][r['id']]['source']}")
            batch.put_file(io.BytesIO(buf.getvalue().encode()), f'/{sp}/clips.csv')
            batch.put_file(io.BytesIO(json.dumps(manifest).encode()), f'/{sp}/manifest.json')
    for sp in speakers:
        convert.remote(sp)


def _check_eval_request(split, final_test):
    if split not in ('validation', 'test'):
        raise ValueError('split must be validation or test')
    if split == 'test' and not final_test:
        raise ValueError('Freeze model choice first, then use --split test --final-test. Never tune on these scores.')


@app.local_entrypoint()
def baseline(speaker: str = "S1", data_dir: str = "../hack-speech", split: str = 'validation', final_test: bool = False):
    _check_eval_request(split, final_test)
    rows, meta = run_baseline.remote(speaker, split)
    out = _results(data_dir) / f"{speaker}__stock-whisper-turbo__{split}.csv"
    write_csv(out, rows, ["id", "condition", "reference", "hypothesis"])
    out.with_suffix('.json').write_text(json.dumps(meta, indent=2))


@app.local_entrypoint()
def train(speaker: str = "S1", name: str = "s1-whisper-lora-v1", epochs: int = 8,
          lr: float = 1e-4, rank: int = 32, batch: int = 4, accum: int = 2, seed: int = 0):
    cfg = run_train.remote(speaker, name, epochs, lr, rank, batch, accum, seed)
    print(f"done: {name}, best epoch {cfg['best_epoch']}, val WER {cfg['best_val_wer']:.3f}")


@app.local_entrypoint()
def evaluate(speaker: str = "S1", model: str = "s1-whisper-lora-v1",
             data_dir: str = "../hack-speech", split: str = 'validation', final_test: bool = False):
    _check_eval_request(split, final_test)
    rows, cfg = run_evaluate.remote(speaker, model, split)
    out = _results(data_dir) / f"{speaker}__{model}__{split}.csv"
    write_csv(out, rows, ["id", "condition", "reference", "hypothesis", "nbest"])
    out.with_suffix(".json").write_text(json.dumps(cfg, indent=2))


def _wer_rows(system, speaker, items, notes):
    """items: list of (condition, ref, hyp) already normalised."""
    import_ok = True
    try:
        import jiwer
    except ImportError:
        import_ok = False
    out = []
    for cond in ("quiet", "noisy", "all"):
        sel = [(r, h) for c, r, h in items if cond == "all" or c == cond]
        sel = [(r, h) for r, h in sel if r]
        if not sel:
            continue
        if import_ok:
            wer = jiwer.wer([r for r, _ in sel], [h for _, h in sel])
        else:
            wer = _simple_wer([r for r, _ in sel], [h for _, h in sel])
        out.append({"system": system, "speaker": speaker, "condition": cond,
                    "wer": f"{wer:.3f}", "n_clips": len(sel), "notes": notes})
    return out


def _simple_wer(refs, hyps):
    """Corpus WER (word-level edit distance), used if jiwer isn't installed locally."""
    errors = total = 0
    for ref, hyp in zip(refs, hyps):
        r, h = ref.split(), hyp.split()
        d = list(range(len(h) + 1))
        for i in range(1, len(r) + 1):
            prev, d[0] = d[0], i
            for j in range(1, len(h) + 1):
                prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
        errors += d[len(h)]
        total += len(r)
    return errors / max(total, 1)


@app.function(image=image, volumes=VOLS, timeout=600)
def scoring_context(speaker: str, split: str):
    rows, manifest = _verified_rows(speaker)
    _, val, test = _partitions(speaker, rows)
    return val if split == 'validation' else test, manifest


@app.local_entrypoint()
def score(speaker: str = "S1", data_dir: str = "../hack-speech", notes: str = "", split: str = "validation"):
    res = _results(data_dir)
    stamp = datetime.now().strftime("%H:%M")
    if split not in ('validation', 'test'):
        raise ValueError('split must be validation or test')
    selected, manifest = scoring_context.remote(speaker, split)
    clips = {r['id']: r for r in selected}
    systems = []  # (system, [(cond, ref, hyp)], notes)

    for f in sorted(res.glob(f"{speaker}__*__{split}.csv")):
        system = f.stem.split("__", 1)[1]
        rows = list(csv.DictReader(open(f)))
        meta = f.with_suffix(".json")
        if not meta.exists():
            raise ValueError(f'{f}: missing provenance; rerun evaluation')
        c = json.loads(meta.read_text())
        verify_result(rows, c, selected, manifest, CODE_SHA256, split)
        n = f"split={split} code={CODE_SHA256[:12]} {notes}"
        if 'epochs' in c:
            n = (f"epochs={c.get('epochs')} best={c.get('best_epoch')} lr={c.get('lr')} "
                 f"rank={c.get('rank')} n_train={c.get('n_train')} {n}").strip()
        systems.append((system, [(r["condition"], r["reference"], r["hypothesis"]) for r in rows], n))

    lst = Path(data_dir).expanduser() / "listeners.csv"
    if lst.exists() and split == "test":
        by_listener = {}
        for r in csv.DictReader(open(lst)):
            cid = r["id"].strip()
            base = clips.get(cid) or (clips.get(cid[:-1]) if cid.endswith("n") else None)
            if base is None:
                print(f"  listeners.csv: unknown id {cid}, skipped")
                continue
            cond = "noisy" if cid.endswith("n") else base["condition"]
            by_listener.setdefault(r["listener"].strip(), []).append((cond, base["text"], r["heard"]))
        for name, items in sorted(by_listener.items()):
            systems.append((f"listener-{name}", items, notes))

    if not systems:
        raise SystemExit(f"nothing to score in {res} for {speaker}: run baseline or evaluate first")

    flat = [t for _, items, _ in systems for _, r, h in items for t in (r, h)]
    normed = iter(normalize_texts.remote(flat))
    out = []
    for system, items, n in systems:
        items = [(c, next(normed), next(normed)) for c, _, _ in items]
        out += _wer_rows(system, speaker, items, f"{n} @{stamp}".strip())

    path = res / f"scores_{split}_v2.csv"
    new = not path.exists()
    res.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SCORE_COLS)
        if new:
            w.writeheader()
        w.writerows(out)
    print(f"\n{'system':32} {'cond':6} {'WER':>6} {'n':>3}")
    for r in out:
        print(f"{r['system']:32} {r['condition']:6} {r['wer']:>6} {r['n_clips']:>3}")
    print(f"\nappended {len(out)} rows to {path}")


@app.local_entrypoint()
def transcribe(file: str, model: str = "s1-whisper-lora-v1"):
    p = Path(file).expanduser()
    t0 = time.perf_counter()
    nbest, ms = Transcriber(adapter="" if model == "stock" else model).run.remote(
        p.read_bytes(), p.suffix.lower())
    total = round((time.perf_counter() - t0) * 1000)
    print(f"best: {nbest[0]}")
    print("Alternatives are sampled and unranked, not confidence scores; fewer than 5 may be returned.")
    for i, h in enumerate(nbest, 1):
        print(f"  {i}. {h}")
    print(f"model time: {ms} ms   round trip incl. upload/cold start: {total} ms")

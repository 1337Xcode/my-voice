"""Local, dependency-free data and result checks. No cloud calls."""
import hashlib
import json
import re
from pathlib import Path

PIPELINE_VERSION = '2'
DECODING = {'beams': 5, 'max_new_tokens': 128, 'candidate_method': 'beam_top1_plus_unranked_samples', 'seed': 0}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sentence_key(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


def check_duration(n_samples, sample_rate=16000, label='audio'):
    if not 0 < n_samples <= 30 * sample_rate:
        raise ValueError(f'{label}: {n_samples / sample_rate:.2f}s; require 0 < duration <= 30s. Split/re-record with matching transcripts; audio will not be silently truncated.')


def prepare_manifest(root, rows):
    root = Path(root).resolve()
    entries = {}
    for r in rows:
        cid = r['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', cid):
            raise ValueError(f'invalid clip id: {cid}')
        if cid in entries:
            raise ValueError(f'duplicate clip id: {cid}')
        path = (root / r['file']).resolve()
        if not r['file'] or not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'{cid}: missing or invalid audio file: {r["file"]}')
        sha = file_hash(path)
        entries[cid] = {'source': f'incoming/{cid}-{sha}{path.suffix.lower()}', 'sha256': sha}
    return {'rows_sha256': digest(rows), 'entries': entries, 'dataset_sha256': digest([rows, entries])}


def fixed_validation(rows, path):
    """Persist sentence groups once; added training clips cannot move the holdout."""
    path = Path(path)
    groups = {sentence_key(r['text']) for r in rows if r['split'] == 'train'}
    if path.exists():
        keys = json.loads(path.read_text())['sentence_keys']
        if not keys or not set(keys) <= groups:
            raise ValueError('Frozen validation sentences missing/changed. Restore them or start a separately named data experiment.')
    else:
        ordered = sorted(groups, key=lambda s: digest(s))
        if len(ordered) < 2:
            raise ValueError('Need at least two different training sentences for validation.')
        keys = ordered[:max(1, round(len(ordered) * 0.1))]
        path.write_text(json.dumps({'sentence_keys': keys}, indent=2))
    val = [r for r in rows if r['split'] == 'train' and sentence_key(r['text']) in keys]
    train = [r for r in rows if r['split'] == 'train' and sentence_key(r['text']) not in keys]
    return train, val


def unique_candidates(texts, limit):
    # Always preserve beam top-1, even if it is empty. Samples must not replace it.
    first = texts[0].strip()
    result, seen = [first], {sentence_key(first)}
    for text in texts[1:]:
        text = text.strip()
        key = sentence_key(text)
        if key and key not in seen:
            result.append(text)
            seen.add(key)
        if len(result) >= limit:
            break
    return result[:limit]


def verify_result(rows, meta, expected_rows, manifest, code_sha, split):
    if meta.get('pipeline_version') != PIPELINE_VERSION or meta.get('evaluation_code_sha256') != code_sha:
        raise ValueError('Legacy/stale result: rerun baseline/evaluate with this code.')
    if (meta.get('evaluation_dataset_sha256') or meta.get('dataset_sha256')) != manifest['dataset_sha256'] or meta.get('eval_split') != split:
        raise ValueError('Result belongs to a different dataset or split; rerun evaluation.')
    expected = {r['id']: r for r in expected_rows}
    if len(rows) != len(expected) or {r['id'] for r in rows} != set(expected):
        raise ValueError('Result clip set differs from the selected evaluation split.')
    for r in rows:
        if r['reference'] != expected[r['id']]['text'] or r['condition'] != expected[r['id']]['condition']:
            raise ValueError(f'{r["id"]}: stale reference or condition')


def evaluation_record(training_config, metadata):
    """Merge evaluation provenance without overwriting the training data identity.

    training_config must be the original adapter train_config.json, never an
    older evaluation export whose dataset_sha256 may already be overwritten.
    dataset_sha256 remains an evaluation alias for existing v2 readers.
    """
    result = dict(training_config)
    result.pop('history', None)
    training_sha = training_config.get('training_dataset_sha256') or training_config.get('dataset_sha256')
    if not training_sha:
        raise ValueError('Original training dataset hash missing')
    evaluation_sha = metadata.get('evaluation_dataset_sha256') or metadata.get('dataset_sha256')
    if not evaluation_sha:
        raise ValueError('Evaluation dataset hash missing')
    result.update(metadata)
    result['training_dataset_sha256'] = training_sha
    result['evaluation_dataset_sha256'] = evaluation_sha
    result['dataset_sha256'] = evaluation_sha
    return result

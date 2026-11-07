import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checks import (check_duration, prepare_manifest, fixed_validation,
                    unique_candidates, verify_result, PIPELINE_VERSION, evaluation_record)

class PipelineChecks(unittest.TestCase):
    def test_evaluation_preserves_original_training_provenance(self):
        original = {'dataset_sha256': 'train-A', 'history': [1], 'training_code_sha256': 'old'}
        result = evaluation_record(original, {'dataset_sha256': 'eval-B', 'evaluation_code_sha256': 'new'})
        self.assertEqual(result['training_dataset_sha256'], 'train-A')
        self.assertEqual(result['evaluation_dataset_sha256'], 'eval-B')
        self.assertEqual(result['dataset_sha256'], 'eval-B')
        self.assertEqual(result['training_code_sha256'], 'old')
        self.assertEqual(original['history'], [1])
        self.assertNotIn('history', result)
        explicit = evaluation_record({'training_dataset_sha256': 'train-C', 'dataset_sha256': 'other'},
                                     {'evaluation_dataset_sha256': 'eval-D'})
        self.assertEqual(explicit['training_dataset_sha256'], 'train-C')
        self.assertEqual(explicit['evaluation_dataset_sha256'], 'eval-D')
        with self.assertRaises(ValueError):
            evaluation_record({}, {'dataset_sha256': 'eval'})

    def test_duration_boundaries(self):
        check_duration(480000)
        for length in (0, 480001):
            with self.assertRaises(ValueError):
                check_duration(length)

    def test_upload_missing_duplicate_and_changed_content(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rows = [{'id': 'P1_a', 'file': 'a.wav'}]
            with self.assertRaises(ValueError):
                prepare_manifest(root, rows)
            (root / 'a.wav').write_bytes(b'first')
            first = prepare_manifest(root, rows)
            (root / 'a.wav').write_bytes(b'second')
            second = prepare_manifest(root, rows)
            self.assertNotEqual(first['entries'], second['entries'])
            with self.assertRaises(ValueError):
                prepare_manifest(root, rows * 2)
            with self.assertRaises(ValueError):
                prepare_manifest(root, [{'id': 'a', 'file': '../outside.wav'}])

    def test_frozen_sentence_holdout(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'split.json'
            rows = [{'id': str(i), 'text': f'word {i}', 'split': 'train'} for i in range(10)]
            train, val = fixed_validation(rows, path)
            added = rows + [{'id': 'extra', 'text': 'new sentence', 'split': 'train'},
                            {'id': 'repeat', 'text': val[0]['text'].upper() + '!', 'split': 'train'}]
            train2, val2 = fixed_validation(added, path)
            self.assertEqual({r['id'] for r in val2}, {val[0]['id'], 'repeat'})
            with self.assertRaises(ValueError):
                fixed_validation(train, path)

    def test_candidates_preserve_beam_and_remove_duplicates(self):
        self.assertEqual(unique_candidates(['Hello.', 'hello!', 'Other'], 5), ['Hello.', 'Other'])
        self.assertEqual(unique_candidates(['', 'Other'], 5), ['', 'Other'])
        self.assertEqual(unique_candidates(['a', 'b'], 1), ['a'])

    def test_stale_results_rejected(self):
        expected = [{'id': 'a', 'text': 'hello', 'condition': 'quiet'}]
        results = [{'id': 'a', 'reference': 'hello', 'condition': 'quiet'}]
        manifest = {'dataset_sha256': 'dataset'}
        meta = {'pipeline_version': PIPELINE_VERSION, 'evaluation_code_sha256': 'code',
                'dataset_sha256': 'dataset', 'eval_split': 'validation'}
        verify_result(results, meta, expected, manifest, 'code', 'validation')
        for change in ({'evaluation_code_sha256': 'old'}, {'dataset_sha256': 'old'}, {'eval_split': 'test'}):
            with self.assertRaises(ValueError):
                verify_result(results, dict(meta, **change), expected, manifest, 'code', 'validation')
        for rows in ([], results * 2, [dict(results[0], reference='changed')]):
            with self.assertRaises(ValueError):
                verify_result(rows, meta, expected, manifest, 'code', 'validation')

if __name__ == '__main__':
    unittest.main()

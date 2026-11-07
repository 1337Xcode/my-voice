"""Import and exercise local guards without Modal credentials or cloud calls."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

class Chain:
    def __getattr__(self, name):
        return lambda *a, **k: self

class AppStub:
    def __init__(self, *a):
        pass
    def __getattr__(self, name):
        return lambda *a, **k: lambda fn: fn

stub = types.SimpleNamespace(
    App=AppStub, Image=Chain(), Volume=Chain(), parameter=lambda: None,
    enter=lambda: lambda fn: fn, method=lambda: lambda fn: fn)
spec = importlib.util.spec_from_file_location('pipeline_under_test', Path(__file__).resolve().parents[1] / 'app.py')
pipeline = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'modal': stub}):
    spec.loader.exec_module(pipeline)

class EntrypointChecks(unittest.TestCase):
    def test_test_requires_explicit_flag(self):
        pipeline._check_eval_request('validation', False)
        pipeline._check_eval_request('test', True)
        with self.assertRaises(ValueError):
            pipeline._check_eval_request('test', False)
        with self.assertRaises(ValueError):
            pipeline._check_eval_request('unknown', True)

    def test_sentence_leak_detected(self):
        rows = [{'id': 'a', 'text': 'Hello world.', 'split': 'train'},
                {'id': 'b', 'text': 'HELLO world!', 'split': 'test'}]
        with self.assertRaises(ValueError):
            pipeline.split_rows(rows)

    def test_extra_csv_columns_survive_upload_roundtrip(self):
        import csv, io
        src = ("id,speaker,text,file,split,condition,ok,notes,recorded_by\n"
               "S1_r001,S1,Hello there.,raw/a.m4a,train,quiet,yes,,Data\n")
        local = pipeline.read_clips(src)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=pipeline.CSV_COLS, extrasaction='ignore')
        w.writeheader()
        w.writerows(local)
        remote = pipeline.read_clips(buf.getvalue(), 'S1')
        self.assertEqual(pipeline.digest(local), pipeline.digest(remote))

    def test_image_local_source_is_last_step(self):
        text = (Path(__file__).resolve().parents[1] / 'app.py').read_text()
        block = text[text.index('image = ('):text.index('\n)\n', text.index('image = ('))]
        steps = [l.strip() for l in block.splitlines() if l.strip().startswith('.')]
        self.assertTrue(steps[-1].startswith('.add_local_python_source'), steps[-1])

    def test_corpus_wer_includes_insertions(self):
        self.assertEqual(pipeline._simple_wer(['hello'], ['hello extra words']), 2.0)
        self.assertAlmostEqual(pipeline._simple_wer(['a b', 'c'], ['a', 'c']), 1/3)

if __name__ == '__main__':
    unittest.main()

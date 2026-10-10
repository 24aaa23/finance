"""One combined input must retain all questions and preserve saved inputs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'prepare_dataset.py'
spec = importlib.util.spec_from_file_location('single_dataset', path)
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


class SingleDatasetTests(unittest.TestCase):
    def test_combines_parts_losslessly_and_refuses_changed_saved_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parts = {}
            records = [{'global_question_id': 'A:1', 'question': 'First?', 'ground_truth_answer': '[1,2]'},
                       {'global_question_id': 'B:2', 'question': 'Second?', 'ground_truth_answer': '[]'}]
            for index, record in enumerate(records):
                part = root / f'part{index}.jsonl'
                part.write_text(json.dumps(record) + '\n', encoding='utf-8')
                parts[str(index)] = part
            destination = root / 'output/input_questions.jsonl'
            with patch.object(preparation, 'prepare_question_type_manifests', return_value=parts):
                self.assertEqual(preparation.prepare_dataset(None, None, destination, root), 2)
                saved = destination.read_bytes()
                self.assertEqual([json.loads(line) for line in saved.decode().splitlines()], records)
                self.assertEqual(preparation.prepare_dataset(None, None, destination, root), 2)
                parts['0'].write_text(json.dumps({**records[0], 'question': 'Changed?'}) + '\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Dataset changed'):
                    preparation.prepare_dataset(None, None, destination, root)
                self.assertEqual(destination.read_bytes(), saved)

    def test_duplicate_global_ids_are_rejected_before_writing_combined_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            part = root / 'part.jsonl'
            part.write_text((json.dumps({'global_question_id': 'same', 'question': 'Question?'}) + '\n') * 2,
                            encoding='utf-8')
            destination = root / 'combined.jsonl'
            with patch.object(preparation, 'prepare_question_type_manifests', return_value={'one': part}):
                with self.assertRaisesRegex(ValueError, 'Duplicate global'):
                    preparation.prepare_dataset(None, None, destination, root)
            self.assertFalse(destination.exists())

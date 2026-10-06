"""Prepare the whole local workbook as one lossless question manifest."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from run_pipeline_v2_kg.dataset_batch import prepare_question_type_manifests


def prepare_dataset(workbook, full_answers, destination, parts_dir):
    manifests = prepare_question_type_manifests(workbook, full_answers, parts_dir)
    text = "".join(path.read_text(encoding="utf-8") for path in manifests.values())
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    identifiers = [str(record['global_question_id']) for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Duplicate global question IDs in the combined dataset.')
    if not records or any(not str(record.get('question', '')).strip() for record in records):
        raise ValueError('The dataset must contain nonempty questions.')
    destination = Path(destination)
    if destination.is_file():
        if destination.read_text(encoding="utf-8") != text:
            raise ValueError('Dataset changed since preparation. Preserve pipeline_output_kg_v11 '
                             'before preparing a fresh run.')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=destination.parent, delete=False) as handle:
            handle.write(text)
            temporary = handle.name
        os.replace(temporary, destination)
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=PROJECT_ROOT / 'datatset/wealth_management_1000_test_set_questions.xlsx')
    parser.add_argument('--full-answers', type=Path, default=PROJECT_ROOT / 'datatset/216_questions_full_results.json')
    args = parser.parse_args()
    destination = PROJECT_ROOT / 'pipeline_output_kg_v11/input_questions.jsonl'
    count = prepare_dataset(args.dataset, args.full_answers, destination,
                            PROJECT_ROOT / '.runtime/dataset_parts')
    print(f'[DATASET] {count} questions ready for one sequential run: {destination}', flush=True)


if __name__ == '__main__':
    main()

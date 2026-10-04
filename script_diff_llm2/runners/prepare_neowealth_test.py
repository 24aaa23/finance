"""Prepare evaluation input only; never expose gold SQL to pipeline operators."""
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'neowealth-master-question-bank_FINAL_DELIVERABLE.xlsx'
TARGET = ROOT / 'data/benchmarks/neowealth_test.csv'


def main():
    questions = pd.read_excel(SOURCE, sheet_name='questions', keep_default_na=False)
    gold = pd.read_excel(SOURCE, sheet_name='gold_answers', keep_default_na=False)
    if questions['task_id'].duplicated().any():
        raise ValueError('Duplicate workbook task IDs')
    cells = defaultdict(dict)
    known = set(questions['task_id'])
    for row in gold.itertuples(index=False):
        if row.task_id not in known:
            raise ValueError(f'Gold row has unknown task ID: {row.task_id}')
        key = (row.task_id, int(row.row_no))
        if row.column_name in cells[key]:
            raise ValueError(f'Duplicate gold cell: {key}, {row.column_name}')
        cells[key][row.column_name] = json.loads(row.value_text)
    by_task = defaultdict(list)
    for (task, number), record in sorted(cells.items()):
        by_task[task].append((number, record))
    rows, recovered = [], []
    for row in questions.itertuples(index=False):
        numbered = by_task[row.task_id]
        answer = [record for _, record in numbered]
        if [number for number, _ in numbered] != list(range(1, int(row.gold_row_count) + 1)):
            raise ValueError(f'Gold row numbering/count mismatch: {row.task_id}')
        try:
            embedded = json.loads(row.ground_truth_answer)
        except json.JSONDecodeError:
            recovered.append(row.task_id)
        else:
            if embedded != answer:
                raise ValueError(f'Gold sheets disagree: {row.task_id}')
        if not str(row.question).strip():
            raise ValueError(f'Empty question: {row.task_id}')
        rows.append({'global_question_id': f'neowealth_test:{row.task_id}',
                     'question_id': row.task_id, 'question': row.question,
                     'ground_truth_answer': json.dumps(answer, ensure_ascii=False, allow_nan=False),
                     'difficulty': row.difficulty, 'category': row.tier_name,
                     'query_type': '', 'source_csv': f'neowealth_test_{row.tier}.csv'})
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(TARGET, index=False)
    print(f'Prepared test dataset: {TARGET}')
    print(f'{len(rows)} questions; {len(recovered)} oversized-answer placeholders reconstructed from gold_answers.')
    print(f'Reconstructed tasks: {", ".join(recovered)}')
    print('Gold SQL is excluded. References are evaluation/reporting data only.')


if __name__ == '__main__':
    main()

"""Bounded scheduling around the unchanged grader's complete row workflow.

Every row is passed through regrade_existing_report, including its resume,
execution-status preservation, strict grading, and optional null review rules.
Only the coordinator writes the combined output.
"""
import concurrent.futures
import csv
import fcntl
import os
import tempfile
from pathlib import Path


def read_rows(path):
    with Path(path).open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_rows(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def parallel_regrade(grader, input_csv, output_csv, client, model, *, workers=2, save_every=1):
    if workers < 1 or save_every < 1:
        raise ValueError('workers and save_every must be positive')
    input_csv, output_csv = Path(input_csv).resolve(), Path(output_csv).resolve()
    if input_csv == output_csv:
        raise ValueError('Raw input and graded output must be different files')
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    # A second parallel wrapper must not compete for the same combined CSV.
    with output_csv.with_suffix(output_csv.suffix + '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f'Another grader already writes {output_csv}') from error
        rows = read_rows(input_csv)
        if not rows:
            raise ValueError('Raw report is empty')
        answer_column = 'New Pipeline Result' if 'New Pipeline Result' in rows[0] else 'Scan Raw Rows'
        required = {'Question', 'Ground Truth', answer_column}
        if not required <= rows[0].keys():
            raise ValueError(f'Missing grading columns: {sorted(required - rows[0].keys())}')
        keys = [grader.grading_input_key(row, answer_column, model) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate grading inputs; cannot safely coordinate resume')
        existing = read_rows(output_csv) if output_csv.exists() else []
        existing_by_key = {(row.get('Grading Input Key'), row.get('Grading Policy')): row for row in existing}
        results = {}
        candidates = {}
        for index, row in enumerate(rows):
            policy = grader.NULL_POLICY_VERSION if grader.is_mc_diverse(row, str(input_csv)) else 'strict_v1'
            candidate = existing_by_key.get((keys[index], policy))
            if candidate:
                # Preserve prior progress in coordinator snapshots until this
                # row has completed the original grader's retry/resume checks.
                results[index] = candidate
                candidates[index] = candidate
        def save():
            write_rows(output_csv, [results[i] for i in sorted(results)])
        with tempfile.TemporaryDirectory(prefix='.parallel_grader_', dir=output_csv.parent) as directory:
            directory = Path(directory)
            def grade_one(index):
                folder = directory / str(index)
                (folder / 'input').mkdir(parents=True)
                (folder / 'output').mkdir()
                # Keep the exact input filename; a legacy null policy uses it
                # when Category is empty.
                raw = folder / 'input' / input_csv.name
                graded = folder / 'output' / output_csv.name
                write_rows(raw, [rows[index]])
                if index in candidates:
                    write_rows(graded, [candidates[index]])
                grader.regrade_existing_report(str(raw), str(graded), client, model)
                completed = read_rows(graded)
                if len(completed) != 1 or completed[0].get('Grading Input Key') != keys[index]:
                    raise RuntimeError(f'Unexpected grader output at input row {index + 1}')
                return completed[0]
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
            pending = {}
            next_index = 0
            completed_count = 0
            try:
                # Keep only a bounded window in flight; interruptions do not
                # leave hundreds of already-queued API requests running.
                while next_index < len(rows) or pending:
                    while next_index < len(rows) and len(pending) < workers:
                        pending[pool.submit(grade_one, next_index)] = next_index
                        next_index += 1
                    ready, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in ready:
                        index = pending.pop(future)
                        results[index] = future.result()
                        completed_count += 1
                        print(f'[PARALLEL GRADE] {completed_count}/{len(rows)}: row {index + 1} {results[index]["New Status"]}', flush=True)
                        if completed_count % save_every == 0:
                            save()
            finally:
                # Finish the bounded in-flight set and checkpoint it even on
                # Ctrl+C or a worker failure. No new tasks are submitted here.
                pool.shutdown(wait=True, cancel_futures=True)
                for future, index in pending.items():
                    if future.done() and not future.cancelled() and future.exception() is None:
                        results[index] = future.result()
                save()
    return str(output_csv)

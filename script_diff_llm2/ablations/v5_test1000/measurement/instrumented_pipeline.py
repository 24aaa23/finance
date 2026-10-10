"""Process-local instrumentation; production pipeline files are not modified."""
import concurrent.futures
import contextvars
import functools
import inspect
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from openai.resources.chat.completions import Completions
from script_diff_llm.evaluation import benchmark_io

question_id = contextvars.ContextVar('measurement_question', default=None)
lock = threading.Lock()
log_path = Path(os.environ['MEASUREMENT_REQUEST_LOG'])
selection = json.loads(Path(os.environ['MEASUREMENT_SAMPLE']).read_text())
selected = set(selection['sample_ids'])

# Propagate attribution into independent DAG-node worker threads.
original_submit = concurrent.futures.ThreadPoolExecutor.submit
def submit(self, fn, /, *args, **kwargs):
    context = contextvars.copy_context()
    return original_submit(self, context.run, fn, *args, **kwargs)
concurrent.futures.ThreadPoolExecutor.submit = submit

original_record = benchmark_io.run_single_benchmark_record
@functools.wraps(original_record)
def record(row, **kwargs):
    token = question_id.set(str(row['Sample Row ID']))
    try:
        return original_record(row, **kwargs)
    finally:
        question_id.reset(token)
benchmark_io.run_single_benchmark_record = record

original_normalize = benchmark_io.normalize_benchmark_records
def normalize(frame, **kwargs):
    rows, mode = original_normalize(frame, **{**kwargs, 'offset': 0, 'limit': 1000})
    filtered = [row for row in rows if str(row['Sample Row ID']) in selected]
    if len(filtered) != len(selected):
        raise ValueError('Measurement selection no longer matches benchmark IDs')
    return filtered, mode
benchmark_io.normalize_benchmark_records = normalize

original_create = Completions.create
@functools.wraps(original_create)
def create(self, *args, **kwargs):
    if kwargs.get('stream'):
        raise ValueError('This measurement wrapper supports the existing non-streaming pipeline only')
    caller = inspect.currentframe().f_back
    event = {'request_id': str(uuid.uuid4()), 'question_id': question_id.get(),
             'model': kwargs.get('model'), 'stage': caller.f_code.co_name,
             'started_unix': time.time(), 'success': False}
    start = time.perf_counter()
    try:
        response = original_create(self, *args, **kwargs)
        usage = getattr(response, 'usage', None)
        event.update(success=True, usage=usage.model_dump() if usage else None,
                     finish_reasons=[getattr(c, 'finish_reason', None) for c in response.choices])
        return response
    except Exception as error:
        # Avoid storing credentials, prompts, outputs, or provider error bodies.
        event['error_type'] = type(error).__name__
        raise
    finally:
        event['request_seconds'] = time.perf_counter() - start
        with lock:
            with log_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(event) + '\n')
Completions.create = create

runpy.run_path(str(ROOT / 'runners/train/run_pipeline.py'), run_name='__main__')

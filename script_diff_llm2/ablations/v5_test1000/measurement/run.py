#!/usr/bin/env python3
"""Small, shared, stratified usage sample; never starts a grader."""
import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import sys

BASE = Path(__file__).resolve().parent
ABLATION = BASE.parent
sys.path.insert(0, str(ABLATION))
import run_raw
from script_diff_llm.evaluation.benchmark_io import load_input_samples, normalize_benchmark_records


def make_sample(size, seed):
    frame = load_input_samples(str(run_raw.SOURCES['INPUT_SAMPLE_FILE']), 'ALL_BENCHMARK_SHEETS')
    records, _ = normalize_benchmark_records(frame, offset=0, limit=1000)
    groups = collections.defaultdict(list)
    for row in records:
        groups[str(row['Query Type'])].append(row)
    if size < len(groups) or size > len(records):
        raise ValueError(f'Choose between {len(groups)} and {len(records)} questions')
    # Two per type when possible, so within-type variability can be observed.
    minimum = 2 if size >= 2 * len(groups) else 1
    counts = {key: min(minimum, len(groups[key])) for key in groups}
    while sum(counts.values()) < size:
        key = max((k for k in groups if counts[k] < len(groups[k])),
                  key=lambda k: (size * len(groups[k]) / len(records) - counts[k], k))
        counts[key] += 1
    rng = random.Random(seed)
    chosen = []
    for key in sorted(groups):
        # Secondary proportional allocation avoids selecting only one source/difficulty.
        buckets = collections.defaultdict(list)
        for row in groups[key]:
            buckets[(str(row['Difficulty']), str(row['Source CSV']))].append(row)
        allocated = {b: 0 for b in buckets}
        for _ in range(counts[key]):
            b = max((b for b in buckets if allocated[b] < len(buckets[b])),
                    key=lambda b: (counts[key] * len(buckets[b]) / len(groups[key]) - allocated[b], b))
            allocated[b] += 1
        for b in sorted(buckets):
            chosen.extend(rng.sample(buckets[b], allocated[b]))
    return {'size': size, 'seed': seed,
            'dataset_sha256': run_raw.file_hash(run_raw.SOURCES['INPUT_SAMPLE_FILE']),
            'population_counts': {k: len(v) for k, v in sorted(groups.items())},
            'sample_counts': counts,
            'sample_ids': [str(r['Sample Row ID']) for r in chosen],
            'metadata': {str(r['Sample Row ID']): {k: r[k] for k in ('Query Type', 'Difficulty', 'Source CSV')}
                         for r in chosen}}


def usage_totals(events, rates):
    input_tokens = output_tokens = 0
    complete = True
    for event in events:
        usage = event.get('usage') or {}
        if not event.get('success') or not isinstance(usage.get('prompt_tokens'), int) or not isinstance(usage.get('completion_tokens'), int):
            complete = False
            continue
        input_tokens += usage['prompt_tokens']
        output_tokens += usage['completion_tokens']
    priced = all(isinstance(rates.get(k), (int, float)) and rates[k] >= 0
                 for k in ('input_per_million', 'output_per_million'))
    cost = ((input_tokens * rates['input_per_million'] + output_tokens * rates['output_per_million']) / 1e6
            if priced and complete else None)
    return {'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'usage_complete': complete, 'cost': cost,
            'request_seconds': sum(e['request_seconds'] for e in events), 'calls': len(events)}


def summarize(folder, sample, rates):
    csv.field_size_limit(sys.maxsize)
    raw = folder / 'raw_pipeline.csv'
    if not raw.exists():
        return {'status': 'not started'}
    with raw.open() as handle:
        rows = list(csv.DictReader(handle))
    log = folder / 'requests.jsonl'
    events = []
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # In-progress final write; a later summary will read it.
    by_id = collections.defaultdict(list)
    for event in events:
        by_id[event.get('question_id')].append(event)
    strata = collections.defaultdict(list)
    question_metrics = []
    for row in rows:
        key = str(row['Sample Row ID'])
        values = usage_totals(by_id[key], rates)
        values.update(sample_row_id=key, query_type=sample['metadata'][key]['Query Type'],
                      elapsed_seconds=float(row['Elapsed Seconds']), status=row['New Status'])
        # A question that failed before making any model calls legitimately costs zero.
        strata[values['query_type']].append(values)
        question_metrics.append(values)
    complete = len(rows) == sample['size'] and set(strata) == set(sample['population_counts'])
    all_usage = all(q['usage_complete'] for q in question_metrics)

    def estimate(groups):
        weights = {k: n / sum(sample['population_counts'].values())
                   for k, n in sample['population_counts'].items()}
        def mean(field):
            return sum(weights[k] * statistics.mean(x[field] for x in groups[k]) for k in weights)
        tokens = mean('output_tokens')
        return {'request_latency_ms_per_output_token': mean('request_seconds') * 1000 / tokens if tokens else None,
                'average_cost_per_question': mean('cost') if all(q['cost'] is not None for v in groups.values() for q in v) else None,
                'mean_input_tokens_per_question': mean('input_tokens'),
                'mean_output_tokens_per_question': tokens,
                'mean_model_calls_per_question': mean('calls'),
                'mean_question_elapsed_seconds': mean('elapsed_seconds')}

    result = {'completed': len(rows), 'selected': sample['size'], 'usage_complete': all_usage,
              'sample_complete': complete, 'observed_query_types': {k: len(v) for k, v in strata.items()},
              'startup_context': usage_totals(by_id[None], rates),
              'failed_requests': sum(not e.get('success') for e in events),
              'questions': question_metrics,
              'notes': ['Non-streaming request duration includes network, queueing and SDK retries; not pure generation time.',
                        'completion_tokens uses provider usage, including reasoning if the provider counts it.',
                        'Cost excludes grading; cached preparation is not charged again.',
                        'Small strata and rare long repairs can make 40-question estimates uncertain; inspect intervals.',
                        'Bootstrap intervals quantify sample variation, not provider timing or pricing uncertainty.']}
    if complete and all_usage:
        point = estimate(strata)
        rng = random.Random(12345)
        draws = [estimate({k: rng.choices(v, k=len(v)) for k, v in strata.items()}) for _ in range(1000)]
        intervals = {}
        for key in point:
            vals = sorted(d[key] for d in draws if d[key] is not None)
            intervals[key] = [vals[int(.025 * len(vals))], vals[min(len(vals)-1, int(.975 * len(vals)))]] if vals else None
        result.update(estimates=point, bootstrap_95_percent_intervals=intervals)
        startup = result['startup_context']['cost']
        average = point['average_cost_per_question']
        result['estimated_1000_query_cost_excluding_preparation'] = average * 1000 if average is not None else None
        result['estimated_1000_query_cost_including_observed_preparation'] = average * 1000 + startup if average is not None and startup is not None else None
    else:
        result['estimates'] = None
        result['notes'].append('Final estimates withheld until all selected rows and request usage are available.')
    (folder / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return {k: v for k, v in result.items() if k != 'questions'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', choices=run_raw.MODELS, default=list(run_raw.MODELS))
    parser.add_argument('--conditions', nargs='+', choices=run_raw.CONDITIONS, default=list(run_raw.CONDITIONS))
    parser.add_argument('--sample-size', type=int, default=40)
    parser.add_argument('--seed', type=int, default=20261006)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--tag', default='sample40_01')
    parser.add_argument('--prices', type=Path, default=BASE / 'prices.json')
    parser.add_argument('--select-only', action='store_true', help='Create/inspect selection without API calls')
    parser.add_argument('--summarize-only', action='store_true', help='Recalculate cost after filling prices; no API calls')
    args = parser.parse_args()
    # Reuse existing launcher validation and model/endpoint/context configuration.
    run_raw.load_local_env_file()
    root = BASE / 'runs' / args.tag
    validated = run_raw.parse_args(['gpt_oss_120b', 'without_context', '--run-tag', args.tag,
                                    '--workers', str(args.workers)])
    root.mkdir(parents=True, exist_ok=True)
    sample = make_sample(args.sample_size, args.seed)
    sample_path = root / 'sample.json'
    if sample_path.exists() and json.loads(sample_path.read_text()) != sample:
        raise ValueError('Selection changed. Use a fresh --tag.')
    sample_path.write_text(json.dumps(sample, indent=2) + '\n')
    print('Sample allocation:', sample['sample_counts'], flush=True)
    if args.select_only:
        print('Selection saved:', sample_path)
        return 0
    prices = json.loads(args.prices.read_text())
    summaries = []
    for model in args.models:
        for condition in args.conditions:
            folder = root / model / condition
            if not args.summarize_only:
                validated.model, validated.condition = model, condition
                env, _, experiment = run_raw.build_environment(validated, os.environ)
                folder.mkdir(parents=True, exist_ok=True)
                env.update(PIPELINE_OUTPUT_DIR=str(folder), REPORT_FILE=str(folder / 'raw_pipeline.csv'),
                           RAW_REPORT_FILE=str(folder / 'raw_pipeline.csv'),
                           MEASUREMENT_REQUEST_LOG=str(folder / 'requests.jsonl'),
                           MEASUREMENT_SAMPLE=str(sample_path))
                manifest = run_raw.manifest_for(validated, env, experiment)
                measurement = {'sample': sample, 'instrumentation_sha256': run_raw.file_hash(BASE / 'instrumented_pipeline.py')}
                manifest['signature'] = hashlib.sha256((manifest['signature'] + json.dumps(measurement, sort_keys=True)).encode()).hexdigest()
                manifest['measurement'] = measurement
                run_raw.check_resume(folder, manifest)
                (folder / 'run_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
                code = run_raw.execute_raw([sys.executable, '-u', str(BASE / 'instrumented_pipeline.py'), str(experiment)], env, folder)
                if code:
                    print(f'{model}/{condition} stopped with code {code}; rerun same command to resume.', flush=True)
                    if code == 130:
                        return code
            summary = summarize(folder, sample, prices.get(model, {}))
            summary['pricing'] = {'currency': prices.get('currency'),
                                  'basis': prices.get('pricing_basis', 'Rates supplied in pricing file'),
                                  'rates': prices.get(model, {})}
            if (folder / 'summary.json').exists():
                detailed = json.loads((folder / 'summary.json').read_text())
                detailed['pricing'] = summary['pricing']
                (folder / 'summary.json').write_text(json.dumps(detailed, indent=2) + '\n')
            summaries.append({'model': model, 'condition': condition, **summary})
            print(json.dumps({'model': model, 'condition': condition, 'estimates': summary.get('estimates')}, indent=2))
    (root / 'combined_summary.json').write_text(json.dumps({'currency': prices.get('currency'), 'pricing_basis': prices.get('pricing_basis'), 'experiments': summaries}, indent=2) + '\n')
    with (root / 'summary_table.csv').open('w', newline='') as handle:
        fields = ['model', 'condition', 'completed', 'selected', 'request_latency_ms_per_output_token',
                  'latency_95_percent_interval', 'average_cost_per_question', 'cost_95_percent_interval', 'currency', 'pricing_basis']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for summary in summaries:
            estimates = summary.get('estimates') or {}
            intervals = summary.get('bootstrap_95_percent_intervals') or {}
            writer.writerow({'model': summary['model'], 'condition': summary['condition'],
                             'completed': summary.get('completed', 0), 'selected': sample['size'],
                             'request_latency_ms_per_output_token': estimates.get('request_latency_ms_per_output_token'),
                             'latency_95_percent_interval': intervals.get('request_latency_ms_per_output_token'),
                             'average_cost_per_question': estimates.get('average_cost_per_question'),
                             'cost_95_percent_interval': intervals.get('average_cost_per_question'),
                             'currency': prices.get('currency'), 'pricing_basis': prices.get('pricing_basis')})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

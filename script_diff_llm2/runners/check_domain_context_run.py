"""Prevent the context launcher resuming rows under changed document settings."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def context_inputs(base_dir, environ):
    inputs = {}
    for variable in ('DOMAIN_INTRO_FILE', 'BUSINESS_RULES_FILE', 'DOMAIN_CONTEXT_APPROVAL_FILE'):
        supplied = environ.get(variable, '').strip()
        if not supplied:
            inputs[variable] = None
            continue
        path = Path(supplied)
        if not path.is_absolute():
            path = Path(base_dir) / path
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest = None  # Missing optional inputs still fall back at runtime.
        inputs[variable] = {'path': str(path.resolve()), 'sha256': digest}
    return inputs


def check_run(output_dir, inputs):
    output_dir = Path(output_dir)
    manifest = output_dir / 'domain_context_inputs.json'
    raw = output_dir / 'raw_pipeline.csv'
    if raw.exists() and raw.stat().st_size:
        if not manifest.exists() or json.loads(manifest.read_text(encoding='utf-8')) != inputs:
            raise ValueError('Existing raw report has different or untracked context inputs. Set V5_OUTPUT_DIR to a fresh directory.')
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(inputs, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    try:
        check_run(args.output_dir, context_inputs(Path(__file__).resolve().parent.parent, os.environ))
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    main()

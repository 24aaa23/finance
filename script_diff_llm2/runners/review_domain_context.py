#!/usr/bin/env python3
"""Inspect preparation results; approve selected, independently reviewed entries."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review', type=Path)
    parser.add_argument('--approve', nargs='+', metavar='RULE_ID', help='Only IDs you have independently reviewed')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    payload = json.loads(args.review.read_text(encoding='utf-8'))
    entries = payload['review']
    if not args.approve:
        for item in payload.get('quarantined_documents', []):
            print(json.dumps(item, indent=2, ensure_ascii=False))
        for entry in entries:
            print(json.dumps({key: entry.get(key) for key in ('id', 'kind', 'document', 'source', 'fields', 'terms', 'definition', 'quote', 'conflicts', 'errors', 'active')}, indent=2, ensure_ascii=False))
        return
    if not args.output:
        parser.error('--output is required with --approve')
    approved = {}
    for identifier in args.approve:
        matches = [entry for entry in entries if entry['id'] == identifier]
        if len(matches) != 1 or matches[0]['errors']:
            parser.error(f'{identifier}: unknown, duplicate, conflicting or ineligible entry')
        approved[identifier] = matches[0]['evidence_hash']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'fingerprint': payload['fingerprint'], 'approved': approved}, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(approved)} approvals to {args.output}')


if __name__ == '__main__':
    main()

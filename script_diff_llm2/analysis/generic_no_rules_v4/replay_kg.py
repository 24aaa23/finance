"""Offline read-only check of rejected RDF queries; never used by the pipeline."""
import json
import urllib.parse
import urllib.request

from analyze import OUT, RUN, read


def main():
    rows = read(RUN / 'raw_pipeline.csv')
    results = {}
    for sample in ('RC125-089', 'RC125-092', 'RC125-103', 'RC125-107'):
        row = next(row for row in rows if row['Sample Row ID'].endswith(':' + sample))
        query = next(node['generated_sparql'] for node in json.loads(row['Node Traces']).values()
                     if node.get('generated_sparql'))
        reference = json.loads(row['Ground Truth'])
        item = {'sparql': query, 'reference_row_count': len(reference)}
        try:
            request = urllib.request.Request('http://127.0.0.1:3030/wealth/query',
                data=urllib.parse.urlencode({'query': query}).encode(),
                headers={'Accept': 'application/sparql-results+json'})
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.load(response)['results']['bindings']
            actual = {result['investorId']['value'] for result in data}
            expected = {result.get('investor_id', result.get('investorId')) for result in reference}
            item.update(row_count=len(data), expected_ids_count=len(expected), exact_id_set_match=actual == expected)
        except Exception as error:
            item['replay_error'] = str(error)
        results[sample] = item
    (OUT / 'read_only_replays.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({sample: {key: value for key, value in item.items() if key != 'sparql'}
                      for sample, item in results.items()}, indent=2))


if __name__ == '__main__':
    main()

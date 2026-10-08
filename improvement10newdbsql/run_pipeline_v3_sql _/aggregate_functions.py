"""Shared aggregate names and continuous-percentile parameter validation."""
import math
import re


AGGREGATIONS = {'sum', 'avg', 'average', 'mean', 'count', 'count_rows',
                'count_distinct', 'nunique', 'min', 'max', 'median',
                'percentile', 'percentile_cont', 'quantile'}


def aggregate_name(operation):
    name = str(operation or '').strip().lower()
    return name in AGGREGATIONS or re.fullmatch(r'percentile_\d+(?:\.\d+)?', name) is not None


def normalize_aggregate(operation, options=None):
    name = str(operation or '').strip().lower()
    name = {'mean': 'avg', 'average': 'avg', 'nunique': 'count_distinct'}.get(name, name)
    options = options or {}
    embedded = re.fullmatch(r'percentile_(\d+(?:\.\d+)?)', name)
    parameters = [options[key] for key in ('quantile', 'q', 'percentile') if key in options]
    if name == 'median':
        parameters.insert(0, 0.5)
    elif embedded:
        parameters.insert(0, float(embedded.group(1)) / 100)
    if name in {'median', 'percentile', 'percentile_cont', 'quantile'} or embedded:
        if not parameters:
            raise ValueError('percentile_cont requires quantile between 0 and 1.')
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or not 0 <= value <= 1 for value in parameters):
            raise ValueError('quantile must be a finite number between 0 and 1.')
        if any(value != parameters[0] for value in parameters[1:]):
            raise ValueError('Conflicting percentile parameters.')
        return ('median' if name == 'median' else 'percentile_cont'), float(parameters[0])
    return name, None

"""Explicit date and ordered-window primitives for the restricted interpreter."""
import pandas as pd

ARITIES = {'date': (1, 1), 'datetime': (1, 1), 'date_diff': (3, 3), 'datediff': (3, 3),
           'dateadd': (3, 3), 'date_add': (3, 3), 'date_trunc': (2, 2),
           'year': (1, 1), 'month': (1, 1), 'day': (1, 1), 'quarter': (1, 1),
           'lag': (1, 3), 'lead': (1, 3), 'rolling_mean': (2, 3), 'rolling_sum': (2, 3),
           'row_number': (0, 0)}


def datetime_values(value, index):
    values = value if isinstance(value, pd.Series) else pd.Series(value, index=index, dtype=object)
    # Numeric date inputs are ambiguous (epoch days, seconds, nanoseconds).
    if any(isinstance(v, (int, float, bool)) for v in values.dropna()):
        raise ValueError('Dates must be explicit ISO date strings or datetime values, not numeric epochs.')
    converted = pd.to_datetime(values, errors='coerce', utc=True, format='mixed')
    if (values.notna() & converted.isna()).any():
        raise ValueError('Invalid date value; use ISO dates or explicit date operands.')
    return converted


def temporal_call(name, args, index):
    def integer(value, low, high, label):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{label} must be an integer literal between {low} and {high}.')
        return value
    def values(value):
        return value if isinstance(value, pd.Series) else pd.Series(value, index=index, dtype=object)
    def dates(value):
        return datetime_values(value, index)
    def unit(value):
        if not isinstance(value, str):
            raise ValueError('Date unit must be a literal string.')
        return value.lower().rstrip('s')
    if name == 'row_number':
        return pd.Series(range(1, len(index) + 1), index=index)
    if name in {'lag', 'lead'}:
        offset = integer(args[1] if len(args) > 1 else 1, 0, 100000, 'Window offset')
        result = values(args[0]).shift(offset if name == 'lag' else -offset)
        if len(args) == 3:
            # Default fills out-of-range rows only; preserve in-range NULLs.
            positions = pd.Series(range(len(index)), index=index)
            outside = positions < offset if name == 'lag' else positions >= len(index) - offset
            result = result.astype(object).where(~outside, args[2])
        return result
    if name in {'rolling_mean', 'rolling_sum'}:
        window = integer(args[1], 1, 100000, 'Rolling window')
        minimum = integer(args[2] if len(args) > 2 else window, 1, window, 'Minimum observations')
        raw = values(args[0])
        number = pd.to_numeric(raw, errors='coerce')
        if (raw.notna() & number.isna()).any():
            raise ValueError('Rolling calculations require numeric inputs.')
        roll = number.rolling(window, min_periods=minimum)
        return roll.mean() if name == 'rolling_mean' else roll.sum()
    if name in {'date', 'datetime'}:
        result = dates(args[0])
        return result.dt.normalize() if name == 'date' else result
    if name in {'year', 'month', 'day', 'quarter'}:
        return getattr(dates(args[0]).dt, name).astype('Int64')
    if name in {'date_diff', 'datediff'}:
        part = unit(args[0])
        start, end = dates(args[1]), dates(args[2])
        if part in {'day', 'hour', 'minute', 'second'}:
            scale = {'day': 86400, 'hour': 3600, 'minute': 60, 'second': 1}[part]
            # SQL boundary counts, including negative intervals.
            freq = {'day': 'D', 'hour': 'h', 'minute': 'min', 'second': 's'}[part]
            return (end.dt.floor(freq) - start.dt.floor(freq)).dt.total_seconds() / scale
        if part in {'month', 'quarter', 'year'}:
            result = end.dt.year - start.dt.year
            if part == 'month':
                result = result * 12 + end.dt.month - start.dt.month
            elif part == 'quarter':
                result = result * 4 + end.dt.quarter - start.dt.quarter
            return result.mask(start.isna() | end.isna())
        raise ValueError('Unsupported date difference unit: ' + part)
    if name in {'dateadd', 'date_add'}:
        part = unit(args[0])
        offset = integer(args[1], -10000, 10000, 'Date offset')
        if part not in {'day', 'month', 'year', 'hour', 'minute', 'second', 'quarter'}:
            raise ValueError('Unsupported date addition unit: ' + part)
        options = {'months': offset * 3} if part == 'quarter' else {part + 's': offset}
        return dates(args[2]).map(lambda value: value + pd.DateOffset(**options) if pd.notna(value) else value)
    if name == 'date_trunc':
        part = unit(args[0])
        raw = dates(args[1])
        if part == 'day':
            return raw.dt.normalize()
        if part not in {'month', 'quarter', 'year'}:
            raise ValueError('Unsupported date truncation unit: ' + part)
        month = raw.dt.month if part == 'month' else ((raw.dt.month - 1) // 3) * 3 + 1 if part == 'quarter' else 1
        components = pd.DataFrame({'year': raw.dt.year, 'month': month, 'day': 1}, index=index)
        return pd.to_datetime(components, errors='coerce', utc=True)
    raise ValueError('Unsupported temporal function: ' + name)

"""Transient-error retry and terminal reporting for SQL-only experiments."""
import json
import re

DIAGNOSTIC_FIELDS = ('Scan Error', 'Pre Scan Validation Reason', 'Validation Reason',
                     'New Pipeline Result', 'Node Traces')
TRANSIENT_PATTERNS = (
    'rate_limit_exceeded', 'throttlingexception', 'too many requests', 'too much usage',
    'insufficient_quota', 'quota_exhausted', 'credit_balance_exhausted',
    'apiconnectionerror', 'connection error', 'apitimeouterror', 'request timed out',
    'read timed out', 'connect timeout', 'connection reset', 'serviceunavailable',
    'service unavailable', 'temporarily unavailable', 'internalservererror',
)


def diagnostics(row):
    parts=[]
    for key in DIAGNOSTIC_FIELDS:
        value=str(row.get(key) or '')
        if key == 'Node Traces':
            try:
                traces=json.loads(value)
            except (ValueError,TypeError):
                continue
            def visit(item):
                if isinstance(item,dict):
                    for name,v in item.items():
                        if any(word in name.lower() for word in ('error', 'reason', 'exception')) and isinstance(v,str):
                            parts.append(v)
                        elif isinstance(v,(list,dict)):visit(v)
                elif isinstance(item,list):
                    for v in item:visit(v)
            visit(traces)
        elif value:
            parts.append(value)
    return '\n'.join(parts)


def is_transient_failure(row):
    status=str(row.get('New Status') or '').upper()
    if status == 'PIPELINE_SUCCESS':return False
    if status in {'TRANSIENT_ERROR','QUOTA_EXHAUSTED'}:return True
    text=diagnostics(row).lower()
    return any(pattern in text for pattern in TRANSIENT_PATTERNS) or bool(
        re.search(r'(?:error code|status code|http)[\s:=-]+(?:429|500|502|503|504)\b',text))


def error_summary(row):
    parts=diagnostics(row).splitlines()
    # Prefer actual API errors over the outer DAG failure summary.
    for text in parts:
        if any(pattern in text.lower() for pattern in TRANSIENT_PATTERNS) or re.search(r'Error code: \d+',text):
            return text[:900]
    for field in ('Pre Scan Validation Reason','Validation Reason','Scan Error','New Pipeline Result'):
        if row.get(field):return str(row[field]).replace('\n',' ')[:900]
    return 'No detailed error was saved; inspect this worker pipeline.log.'


def filter_resume_state(state):
    retry_ids={str(row['Sample Row ID']) for row in state.results_list if is_transient_failure(row)}
    if not retry_ids:return state
    kept=[row for row in state.results_list if str(row['Sample Row ID']) not in retry_ids]
    return state.__class__(kept,state.completed_row_ids-retry_ids,
                           state.retry_count+len(retry_ids),state.resume_enabled)

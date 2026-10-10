"""Separate provider/transport failures from local plan and programming errors."""


def is_quota_exhaustion_error(error):
    text = str(error or '').lower()
    if any(marker in text for marker in ('insufficient_quota', 'exceeded your current quota',
                                         'credit_balance_exhausted', 'no credits remaining')):
        return True
    request_limit = any(marker in text for marker in ('rate_limit_exceeded', 'rate_limit_error',
                                                     'too many requests', 'throttlingexception'))
    return 'error code: 429' in text and 'quota' in text and not request_limit


def is_transient_connection_error(error):
    """The SDK already retries; exhausted transient calls remain resumable."""
    if is_quota_exhaustion_error(error):
        return False
    text = str(error or '').lower()
    status = getattr(error, 'status_code', None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    markers = ('connection error', 'connection refused', 'connection reset',
               'read timed out', 'connect timeout', 'service unavailable',
               'temporarily unavailable', 'gateway timeout', 'rate_limit_exceeded',
               'rate_limit_error', 'too many requests', 'throttlingexception')
    return any(marker in text for marker in markers)

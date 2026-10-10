# Decomposition retries

The main planner makes one initial decomposition request and allows three further
requests if the proposed DAG fails existing shape, scope, operator, binding,
backend, cycle or final-result checks. Each repair receives the original question,
the rejected proposal and the validation reason, alongside the usual schema and
applicable terminology. No benchmark answers or grader feedback are supplied.

A valid single-node plan passes immediately. After four unsuccessful proposals,
the planner uses the existing single-query fallback and preserves the full
question. These are validation-driven repairs, not a new semantic-review agent.

Terminal messages prefixed `[DAG RETRY]` show failures and exhaustion. DAG graph
metadata contains attempt count, failure reasons and a fallback flag; these
fields are not yet separate benchmark CSV columns.

This change applies to the shared main pipeline, including its SQL-only ablation.
Original Improvement10/11 snapshots are unchanged. Valid plans add no model calls;
invalid plans can add three calls and associated latency/cost. SDK transport
retries can additionally occur within each request.

Use a new run tag for a clean comparison: launchers that fingerprint implementation
files will reject resuming an older manifest with changed source code. Already
running Python workers retain the code they loaded at startup.

# Optional database context agent

The v5 pipeline accepts `DOMAIN_INTRO_FILE` and `BUSINESS_RULES_FILE`. Neither is
set by default; documents are never discovered automatically. Relative document
and approval paths are resolved from `script_diff_llm2`.

Preparation runs once at startup using the QuerySpec client/model. Results are
cached by document content/path, runtime schema, preparation version and model.
No preparation calls, additional prompt text or context trace are added when
paths are unset. Missing files warn and are ignored; preparation/API/JSON failures
fall back to the existing pipeline. If one document remains usable, it can still
be prepared. `DOMAIN_CONTEXT_CACHE_DIR` optionally changes the cache directory.

The agent extracts source quotations, mapped fields, kinds, canonical topics and
conflicts. Python validates physical sources/fields, literal evidence, duplicate
IDs and conflicting topic definitions. This checks structural grounding, not the
truth of a formula or the completeness of the agent's conflict detection.

Schema-grounded, nonconflicting **terminology** is eligible automatically.
**Definitions, defaults, constraints and advisory policies require independent
review and hash-bound approval**. A preparation agent is not an approval authority.
Any document containing ground-truth/disputed-question/correction markers is
excluded from the preparation prompt and inference wholesale. The current
`phase0_business_rules.md` is therefore flagged in the review JSON but its contents
are not sent to the agent. It cannot be activated by an approval manifest.
Create a separately source-owned document for independently confirmed definitions;
do not merely remove markers from evaluation-derived rules to activate them.

Decomposition receives only question-matching terminology. QuerySpec receives
question-matching active entries for its backend and retrieved physical sources.
The same selected context is supplied to all QuerySpec repair requests. Instructions
require operational meaning to be represented in the existing computation fields;
SQL/SPARQL generation and validation continue through the existing QuerySpec path.
There is no new final computation layer. `domain_context_trace` records the context
fingerprint and entries made available, not a claim that every entry was applied.

Defaults cannot override explicit requests. Advisory rules cannot add filtering
or computation. Conflicts with mandatory constraints should be unresolved rather
than silently rewriting the question. These are model instructions; candidate
review and comparison of actual plans remain necessary. Accuracy improvement has
not been measured. The grader is unchanged.

## Prepare and review without running benchmark questions

Fuseki and normal model credentials must be available. The opt-in launcher supplies
the two default document paths and a separate output directory; override their
environment variables to use other files. Set a file variable to an empty string
to omit that document:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash runners/run_domain_context_v5.sh prepare
```

The log prints the review JSON path under `outputs/domain_context`. Review it:

```bash
/usr/bin/python3 runners/review_domain_context.py /absolute/path/to/REVIEW.json
```

After independently confirming selected definitions/policies, use their actual
IDs from the review file (the ID below is a placeholder):

```bash
/usr/bin/python3 runners/review_domain_context.py /absolute/path/to/REVIEW.json \
  --approve VERIFIED_RULE_ID \
  --output "$PWD/domain_context_approval.json"
export DOMAIN_CONTEXT_APPROVAL_FILE="$PWD/domain_context_approval.json"
```

Approvals are invalidated on document/schema/model changes. The command refuses
blocked, conflicting, duplicate and unknown IDs. Do not approve entries using
benchmark reference answers. If nothing is approved, only eligible terminology
can be active.

## Run raw pipeline and unchanged grader

After reviewing candidates (and optionally exporting `DOMAIN_CONTEXT_APPROVAL_FILE`):

```bash
bash runners/run_domain_context_v5.sh all
```

Use a new `V5_OUTPUT_DIR` when changing the context or approvals. Existing raw
reports resume completed rows and must not mix different context versions.
The context launcher saves document/approval paths and hashes in
`domain_context_inputs.json`. It refuses to resume a nonempty raw report with changed
or untracked context inputs. This guard checks document settings, not database data
or model settings; use fresh output directories for those changes too. The generic
launcher retains its original behavior and does not apply this guard.
Preparation-only mode does not generate a raw report; use the `prepare` mode.
No full paid benchmark was executed as part of implementing this feature.

## Run the original generic v5 path

```bash
unset DOMAIN_INTRO_FILE BUSINESS_RULES_FILE DOMAIN_CONTEXT_APPROVAL_FILE
unset DOMAIN_CONTEXT_PREPARE_ONLY DOMAIN_CONTEXT_CACHE_DIR V5_OUTPUT_DIR
bash runners/run_generic_v5.sh all
```

Changing databases requires updating the normal source configuration as well as
these documents. Documents cannot supply missing SQL/RDF data. Keep exact schema
mappings and independent provenance in the new documents; there are no financial
thresholds, table names or source-specific formulas hardcoded in the context agent.

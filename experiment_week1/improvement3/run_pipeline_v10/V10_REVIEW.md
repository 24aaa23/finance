# V10 plan review - 14 September 2026

The five edits from the supplied conversation were present, but the result was
not fully correct. This review fixes the problems inside V10. The supplied V10
matched V7 except for three prompt files; it did not implement the separate V8
comparative-contract plan shown in the IDE. That larger design is outside this
approved, simple prompt-focused revision.

| Planned behavior | Finding and correction |
| --- | --- |
| Improve comparative aggregation | The new blanket "compare implies per-entity AVG then AVG" instruction contradicted the existing weighting guidance and could replace a required SUM/MAX. Follow the requested metric and weighting; preserve inner SUM/MAX/AVG and use the appropriate count operation. Ambiguous wording still cannot establish the reference SQL's unstated definitions. |
| Preserve missing dimension groups | Keep left joins for optional label/profile enrichment, while enforcing required participants and explicit filters. The worked example now uses a left profile join, and its SQL comparison includes a participant with no profile row. |
| Group by the requested dimension | Use the owning source's dimension text for category comparisons. Retain identity keys for per-entity summaries and entity-level output so different entities sharing a label do not collapse. |
| Keep grouping attributes optional | Retained. Clarified that optional binding does not cancel ranges, negation, equality, or null/presence predicates. The existing schema-driven normalization already makes known non-subject fields optional. |
| Fix optional SPARQL/filter behavior | Corrected the instruction to place row-eligibility filters outside the optional binding. A filter inside OPTIONAL preserves nonmatching rows with an unbound value; it does not enforce eligibility. Added executable range, missing-value, and present-value examples, and aligned Refine's guidance. |

The filter correction follows the [W3C OPTIONAL semantics](https://www.w3.org/TR/sparql11-query/#OptionalMatching).
It is also checked by executing the actual prompt examples on an RDF fixture and
comparing the results with independent SQLite conditions.

Additional execution defects were found and fixed:

- `run.py` imported `run_pipeline_v7.main`, bypassing every V10 prompt edit. It
  now launches V10, including when called from a different working directory.
- Default version/report names still said V4 and shared the older output folder.
  Defaults now identify V10 and write to `run_pipeline_v10/outputs`.
- The default workbook under `improvement3/dataset` did not exist. The default
  now points to the existing workbook named in the supplied conversation under
  `query_specs_improevemnt/improvement1/dataset`. Environment overrides remain
  supported. Schema and instance file defaults resolve to existing files.

Validation completed:

- **171 offline tests pass**: 167 inherited tests plus four new tests. The existing
  worked-plan test was strengthened to cover a missing profile row as well as a
  null label, unequal fact counts, and required fact-source participation.
- All **63 Python files compile**, including the real prompt f-strings. The
  interrupted shell snippet in the supplied conversation was not sufficient
  evidence of prompt correctness; these checks execute the actual builders.
- The suite checks bounded self-healing: four Final_Spec attempts, failed-plan and
  schema feedback, Query_Spec repair, Scan repair, and missing-source handoff.
- Production imports resolve to V10. No live model, Fuseki, or grader evaluation
  was run. Offline tests use mocked clients; grader authentication messages in
  their output are intentional fixtures.
- The grader file is unchanged. No new operators, deterministic semantic gates,
  question-ID rules, expected answers, or reference SQL were added to inference.

Repeat the offline checks from the workspace root:

```powershell
python -m unittest discover -s experiment_week1/improvement3/run_pipeline_v10/tests -q
```

The corrected launcher is:

```powershell
python experiment_week1/improvement3/run_pipeline_v10/run.py
```

Existing terminal and `.env` settings still override defaults. Use a fresh
`REPORT_FILE` for a new evaluation; the existing source/data manifest check
prevents mixing runs with changed code. The unchanged grader retains its older
default paths, so explicitly select the V10 reports when grading:

```powershell
$env:RAW_REPORT_FILE = 'experiment_week1/improvement3/run_pipeline_v10/outputs/raw_pipeline_v10.csv'
$env:GRADED_REPORT_FILE = 'experiment_week1/improvement3/run_pipeline_v10/outputs/graded_pipeline_v10.csv'
python experiment_week1/improvement3/run_pipeline_v10/grade_final_answers.py --dry-run
```

After the raw report exists, remove `--dry-run` to grade it. Use the actual report
path if it was overridden. No new accuracy number is established by this review.
The LLM can still choose an executable but semantically wrong plan or SPARQL;
parser and runtime checks do not prove equivalence to the question. A fresh matched
evaluation is needed to measure whether retrieval and comparative accuracy improve.

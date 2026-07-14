# LaTeX research-paper draft

Main source:

```text
main.tex
```

Compile with a standard TeX installation:

```bash
pdflatex main.tex
pdflatex main.tex
```

The second pass resolves references and figure/table numbering.

The paper is grounded in the completed 300-row reports:

- `Pipeline_Retest_Report_qwen14b.csv`
- `Pipeline_Retest_Report_qwen14b_all_local.csv`
- `Pipeline_Retest_Report_gemma4_26b.csv`

The exact aggregate values used in the paper are also preserved in:

```text
metrics_snapshot.csv
```

Important: the draft explicitly documents experimental confounds, including
non-uniform final graders, the timing of alias-map improvements, duplicate
questions, and the misleading pipeline-version metadata in the Gemma report.

No TeX compiler was available in the current environment. The source passed
basic structural checks for balanced braces, matching environments, references,
and bibliography keys.

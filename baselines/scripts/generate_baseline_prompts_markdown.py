#!/usr/bin/env python3
"""Generate paper-ready Markdown containing baseline generation prompts only."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
BASELINES = HERE.parent
RESULTS = BASELINES / "results"
OUTPUT = RESULTS / "baseline_generation_prompts_domain_context.md"

DOMAIN_INTRO = BASELINES / "domain_intro.prompt"
BUSINESS_RULES = BASELINES / "phase0_business_rules.md"


def fenced(text: str, language: str = "text") -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}{language}\n{text.rstrip()}\n{fence}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sources() -> None:
    checks = {
        BASELINES / "base_pipeline_qwen" / "run_pipeline.py": [
            "RDF schema:\n{schema_text}",
            "Return only the SPARQL query. Do not include reasoning, explanations, markdown,",
        ],
        BASELINES / "base_pipeline_sql" / "run_pipeline.py": [
            "Database schema (DDL):\n{schema_text}",
            "Return only the SQL query. Do not include reasoning, explanations, markdown,",
        ],
        BASELINES / "graph_rag_local" / "run_pipeline.py": [
            'f"RDF facts:\\n{retrieval[\'context\']}\\n\\n"',
            "Return exactly one JSON object with keys status, answer, and evidence_uris.",
        ],
        BASELINES / "parallel_pipeline_baseline" / "run.py": [
            "RDF schema:\n{schema_text}",
            "Return only the SPARQL query. Do not include reasoning, explanations, markdown,",
        ],
        BASELINES / "parallel_pipeline_sql_baseline" / "run_pipeline.py": [
            "Database schema (DDL):\n{schema_text}",
            "Return only the SQL query. Do not include reasoning, explanations, markdown,",
        ],
        BASELINES / "dail_sql_baseline" / "run_pipeline.py": [
            "/* Some SQL examples are provided based on similar problems: */",
            "Return only the complete SQLite SQL query. Do not include reasoning, explanations, markdown, comments, or prose.",
        ],
    }
    for path, snippets in checks.items():
        source = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in source:
                raise ValueError(f"Prompt source changed; expected snippet missing from {path}: {snippet}")


def direct_sparql_prompt() -> str:
    return """Reference context:
{REFERENCE_CONTEXT}

RDF schema:
{RDF_SCHEMA}

Question:
{QUESTION}

Return only the SPARQL query. Do not include reasoning, explanations, markdown,
comments, or prose."""


def direct_sql_prompt() -> str:
    return """Reference context:
{REFERENCE_CONTEXT}

Database schema (DDL):
{SQLITE_DDL}

Question:
{QUESTION}

Return only the SQL query. Do not include reasoning, explanations, markdown,
comments, or prose."""


def graph_rag_prompt() -> str:
    return """Reference context:
{REFERENCE_CONTEXT}

RDF facts:
{RETRIEVED_RDF_FACTS}

Question:
{QUESTION}

Return exactly one JSON object with keys status, answer, and evidence_uris. Set status to answered or insufficient_evidence."""


def dail_prompt(example_placeholder: str) -> str:
    return f"""Reference context:
{{REFERENCE_CONTEXT}}

/* Some SQL examples are provided based on similar problems: */
{{{example_placeholder}}}

/* Given the following database schema: */
{{SQLITE_DDL}}

/* Answer the following: {{QUESTION}} */

Return only the complete SQLite SQL query. Do not include reasoning, explanations, markdown, comments, or prose."""


def main() -> None:
    validate_sources()
    domain_intro = DOMAIN_INTRO.read_text(encoding="utf-8").strip()
    business_rules = BUSINESS_RULES.read_text(encoding="utf-8").strip()
    reference_wrapper = """Domain introduction:
{DOMAIN_INTRO_CONTENT}

Phase 0 business rules:
{PHASE0_BUSINESS_RULES_CONTENT}"""

    lines = [
        "# Baseline generation prompts", "",
        "This document records the prompts sent to the pipeline-runner models for the six baselines. "
        "It excludes all GPT-5 Mini grading prompts and grading instructions.", "",
        "Every generation request used one `user` message and no separate `system` message. "
        "The model choice changed between runs, but the prompt templates did not.", "",
        "## Placeholder key", "",
        "| Placeholder | Runtime value |",
        "|---|---|",
        "| `{REFERENCE_CONTEXT}` | The domain introduction and Phase 0 business rules, joined using the wrapper below. |",
        "| `{RDF_SCHEMA}` | RDF namespace bindings, classes, properties, and datatypes derived from the active schema and Fuseki metadata. |",
        "| `{SQLITE_DDL}` | `CREATE TABLE` statements read from the active SQLite database. |",
        "| `{RETRIEVED_RDF_FACTS}` | Per-question facts returned by the bounded local GraphRAG retrieval stage. |",
        "| `{QUESTION}` | The current benchmark question. |",
        "| `{PREPASS_EXAMPLE_BLOCKS}` | DAIL-SQL examples selected using masked-question similarity. |",
        "| `{FINAL_EXAMPLE_BLOCKS}` | DAIL-SQL examples reselected using the preliminary SQL skeleton. |", "",
        "Each DAIL-SQL example block has this exact structure:", "",
        fenced("/* Answer the following: {EXAMPLE_QUESTION} */\n{EXAMPLE_SQL}"), "",
        "## Shared reference-context wrapper", "",
        "All six baselines insert the same two files verbatim into `{REFERENCE_CONTEXT}`:", "",
        fenced(reference_wrapper), "",
        "The full contents are reproduced in the appendices.", "",
        f"- `domain_intro.prompt` SHA-256: `{sha256(DOMAIN_INTRO)}`",
        f"- `phase0_business_rules.md` SHA-256: `{sha256(BUSINESS_RULES)}`", "",
        "## Base SPARQL", "",
        "Source: `baselines/base_pipeline_qwen/run_pipeline.py`", "",
        "A single generation call receives the shared reference context, the dynamically constructed RDF schema, and the question.", "",
        fenced(direct_sparql_prompt()), "",
        "## Base SQL", "",
        "Source: `baselines/base_pipeline_sql/run_pipeline.py`", "",
        "A single generation call receives the shared reference context, the SQLite DDL, and the question.", "",
        fenced(direct_sql_prompt()), "",
        "## GraphRAG Local", "",
        "Source: `baselines/graph_rag_local/run_pipeline.py`", "",
        "The retrieval stage is deterministic and does not call an LLM. The sole generation call receives the shared reference context, "
        "the retrieved RDF facts, and the question.", "",
        fenced(graph_rag_prompt()), "",
        "The response contract requires one JSON object with `status`, `answer`, and `evidence_uris`. "
        "A response marked `answered` without a retrieved evidence URI is converted to `insufficient_evidence` by the pipeline.", "",
        "## Parallel SPARQL ensemble", "",
        "Sources: `baselines/parallel_pipeline_baseline/run_pipeline.py` and `baselines/parallel_pipeline_baseline/run.py`", "",
        "Each parallel branch independently receives the same prompt template. The pipeline compares executed result fingerprints for consensus. "
        "The reported run is single-round and does not add repair or grader feedback to generation.", "",
        fenced(direct_sparql_prompt()), "",
        "## Parallel SQL ensemble", "",
        "Source: `baselines/parallel_pipeline_sql_baseline/run_pipeline.py`", "",
        "Each parallel branch independently receives the same prompt template. The pipeline compares executed result fingerprints for consensus.", "",
        fenced(direct_sql_prompt()), "",
        "## DAIL-SQL", "",
        "Source: `baselines/dail_sql_baseline/run_pipeline.py`", "",
        "DAIL-SQL makes two generation calls per question. Both calls use the same structural template and shared context. "
        "Only the selected demonstration examples differ.", "",
        "### Preliminary-SQL call", "",
        "The first call uses examples selected by similarity between schema-masked questions.", "",
        fenced(dail_prompt("PREPASS_EXAMPLE_BLOCKS")), "",
        "### Final-SQL call", "",
        "The preliminary SQL is converted to a schema-masked SQL skeleton. The second call uses examples reselected by question similarity "
        "and skeleton similarity.", "",
        fenced(dail_prompt("FINAL_EXAMPLE_BLOCKS")), "",
        "The preliminary SQL and its skeleton guide example selection only; neither is inserted directly into the final prompt.", "",
        "## Appendix A: domain introduction", "",
        "Source: `baselines/domain_intro.prompt`", "",
        fenced(domain_intro, "markdown"), "",
        "## Appendix B: Phase 0 business rules", "",
        "Source: `baselines/phase0_business_rules.md`", "",
        fenced(business_rules, "markdown"), "",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()

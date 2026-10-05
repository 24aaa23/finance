"""Explicit launch configuration for the isolated improvement7 pipeline."""
import time

CLI_STARTED = time.perf_counter()

import argparse
import os
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from run_pipeline_v2_sql.performance import RunTiming, query_delay
    timing = RunTiming(started=CLI_STARTED)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--retry-errors-in-place", action="store_true",
                        help="Retry only saved execution failures, replacing their rows in --output after backup.")
    parser.add_argument("--query-delay", type=query_delay, default=None,
                        help="Seconds to pause per question; defaults to QUERY_DELAY_SECONDS or 0")
    parser.add_argument("--query-understanding", choices=["on", "off"], default="on")
    parser.add_argument("--contract-checks", choices=["on", "off"], default="on")
    parser.add_argument("--agent-consultation", choices=["on", "off"], default="off",
                        help="Allow bounded specialist requests from planning operators")
    parser.add_argument("--check-inputs", action="store_true", help="Offline input/schema validation; no API calls")
    parser.add_argument("--prepare-knowledge", action="store_true", help="Compile/cache knowledge then stop")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.retry_errors_in_place and (args.limit or args.check_inputs or args.prepare_knowledge):
        parser.error("--retry-errors-in-place cannot be combined with --limit, --check-inputs or --prepare-knowledge")
    if args.retry_errors_in_place and (not args.output or not args.output.is_file()):
        parser.error("--retry-errors-in-place requires --output naming an existing report")
    if not args.db.is_file():
        parser.error("--db must name an existing database")
    if args.questions and not args.questions.is_file():
        parser.error("--questions must name an existing input file")
    if args.env_file and not args.env_file.is_file():
        parser.error("--env-file must name an existing credential file")
    base = Path(__file__).resolve().parent.parent
    if args.check_inputs and args.prepare_knowledge:
        parser.error("Choose only one of --check-inputs or --prepare-knowledge")
    if not args.check_inputs and not args.prepare_knowledge and not args.questions:
        parser.error("--questions is required for a pipeline run")
    os.environ["SQLITE_DB_PATH"] = str(args.db.resolve())
    if args.questions:
        os.environ["INPUT_QUERY_FILE"] = str(args.questions.resolve())
    if args.env_file:
        os.environ["PIPELINE_ENV_FILE"] = str(args.env_file.resolve())
    output = (args.output or base / "outputs" / "run.csv").resolve()
    os.environ["REPORT_FILE"] = str(output)
    os.environ["PIPELINE_OUTPUT_DIR"] = str(output.parent)
    os.environ["TEST_QUERY_LIMIT"] = str(args.limit)
    os.environ["RETRY_ERRORS_IN_PLACE"] = "1" if args.retry_errors_in_place else "0"
    if args.retry_errors_in_place:
        os.environ["RETRY_QUERY_SPEC_ERRORS_ONLY"] = "0"
        os.environ["TEST_QUERY_OFFSET"] = "0"
    if args.query_delay is not None:
        os.environ["QUERY_DELAY_SECONDS"] = str(args.query_delay)
    os.environ["QUERY_UNDERSTANDING"] = "1" if args.query_understanding == "on" else "0"
    os.environ["CONTRACT_CHECKS"] = "1" if args.contract_checks == "on" else "0"
    os.environ["AGENT_CONSULTATION"] = "1" if args.agent_consultation == "on" else "0"
    # Explicit CLI settings win over settings in a selected credential file.
    os.environ["PIPELINE_ENV_OVERRIDE"] = "0"
    if args.check_inputs or args.prepare_knowledge:
        status = "failed"
        mode = "prepare" if args.prepare_knowledge else "check"
        timing_path = base / ".runtime" / "logs" / f"{mode}_{time.time_ns()}_{os.getpid()}.timing.json"
        try:
            with timing.stage("configuration_and_imports"):
                if args.prepare_knowledge:
                    from run_pipeline_v2_sql.common import load_local_env_file
                    load_local_env_file()
                from run_pipeline_v2_sql.knowledge import load_documents, annotate_schema, compile_knowledge
                from run_pipeline_v2_sql.sqlite_backend import load_sqlite_schema
            with timing.stage("schema_and_documents"):
                documents = load_documents(os.getenv("DOMAIN_INTRO_FILE", base / "domain_intro_latest.prompt"),
                                           os.getenv("BUSINESS_RULES_FILE", base / "business_rules_addendum.md"),
                                           os.getenv("TABLE_METADATA_DIR", base / "table_medatada"))
                schema = load_sqlite_schema(args.db)
                annotated = annotate_schema(schema, documents)
            print(f"Validated {len(documents)} documents, {len(schema)} tables, "
                  f"{sum('documentation_source' in t for t in annotated.values())} YAML table matches.")
            if args.prepare_knowledge:
                from run_pipeline_v2_sql.common import GPT_OSS_MODEL, KNOWLEDGE_CACHE_DIR
                from run_pipeline_v2_sql.clients import build_gpt_oss_client
                from run_pipeline_v2_sql.knowledge import digest
                from run_pipeline_v2_sql.knowledge_coverage import coverage_report
                with timing.stage("client_setup"):
                    client = timing.client(build_gpt_oss_client())
                with timing.stage("Domain"):
                    pack, identity = compile_knowledge(documents, schema, client, GPT_OSS_MODEL, KNOWLEDGE_CACHE_DIR)
                timing.metadata.update(knowledge_cache_hit=not timing.llm_calls, knowledge_identity=identity)
                report = coverage_report(pack, documents, identity, digest(pack))
                print(f"[CACHE] Knowledge {'hit' if not timing.llm_calls else 'compiled'}")
                print(f"Compiled {len(pack['rules'])} rules. Identity: {identity}")
                print(f"Coverage: {report['section_count']} sections, {len(report['excluded_sections'])} exclusions.")
                if report["excluded_sections"]:
                    print(f"Exclusions recorded in {Path(KNOWLEDGE_CACHE_DIR) / (identity + '.coverage.json')}; no approval required.")
            status = "completed"
        finally:
            timing.save(timing_path, status)
            print(timing.summary())
            print(f"[TIMING] {timing_path}")
        raise SystemExit(0)
    from run_pipeline_v2_sql.runtime_guard import launch as main
    main(timing=timing)

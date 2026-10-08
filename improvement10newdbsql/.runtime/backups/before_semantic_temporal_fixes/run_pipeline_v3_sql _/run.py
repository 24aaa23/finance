"""Explicit launch configuration for the isolated improvement8 pipeline."""
import time

CLI_STARTED = time.perf_counter()

import argparse
import os
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _bootstrap import bootstrap
    bootstrap()
    from run_pipeline_v3_sql.performance import RunTiming, query_delay
    from run_pipeline_v3_sql.input_paths import add_input_arguments, configure_input_paths
    timing = RunTiming(started=CLI_STARTED)
    parser = argparse.ArgumentParser(description=__doc__)
    add_input_arguments(parser)
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retry-errors-in-place", action="store_true",
                        help="Retry only saved execution failures, replacing their rows in --output after backup.")
    parser.add_argument('--include-pending', action='store_true',
                        help='With retry-errors-in-place, also complete questions not yet saved.')
    parser.add_argument("--query-delay", type=query_delay, default=None,
                        help="Seconds to pause per question; defaults to QUERY_DELAY_SECONDS or 0")
    parser.add_argument("--query-understanding", choices=["on", "off"], default="on")
    parser.add_argument("--contract-checks", choices=["on", "off"], default="on")
    parser.add_argument("--agent-consultation", choices=["on", "off"], default="on",
                        help="Allow on-demand specialist requests without a consultation-count cap (default: on)")
    parser.add_argument("--check-inputs", action="store_true", help="Offline input/schema validation; no API calls")
    parser.add_argument("--prepare-knowledge", action="store_true", help="Compile/cache knowledge then stop")
    parser.add_argument("--knowledge-mode", choices=["simple", "improvement7", "chunked"], default=None,
                        help="Knowledge compiler: simple model draft and review (default), strict improvement7, or chunked")
    parser.add_argument("--knowledge-cache", type=Path,
                        help="Use this saved cache without model compilation; bind selection to current inputs")
    args = parser.parse_args()
    try:
        selected_inputs = configure_input_paths(args, os.environ)
    except ValueError as error:
        parser.error(str(error))
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.retry_errors_in_place and (args.limit or args.check_inputs or args.prepare_knowledge):
        parser.error("--retry-errors-in-place cannot be combined with --limit, --check-inputs or --prepare-knowledge")
    if args.include_pending and not args.retry_errors_in_place:
        parser.error('--include-pending requires --retry-errors-in-place')
    if args.retry_errors_in_place and (not args.output or not args.output.is_file()):
        parser.error("--retry-errors-in-place requires --output naming an existing report")
    if not (args.check_inputs or args.prepare_knowledge) and not args.db.is_file():
        parser.error("--db must name an existing database")
    if args.yaml_dir and not args.yaml_dir.is_dir():
        parser.error("--yaml-dir must name an existing YAML folder")
    if args.questions and not args.questions.is_file():
        parser.error("--questions must name an existing input file")
    if args.env_file and not args.env_file.is_file():
        parser.error("--env-file must name an existing credential file")
    if args.knowledge_cache and not args.knowledge_cache.is_file():
        parser.error("--knowledge-cache must name an existing saved cache")
    base = Path(__file__).resolve().parent.parent
    if args.check_inputs and args.prepare_knowledge:
        parser.error("Choose only one of --check-inputs or --prepare-knowledge")
    if not args.check_inputs and not args.prepare_knowledge and not args.questions:
        parser.error("--questions is required for a pipeline run")
    for name, path in selected_inputs.items():
        print(f"[INPUT] {name}: {path}", flush=True)
    if args.questions:
        os.environ["INPUT_QUERY_FILE"] = str(args.questions.resolve())
    if args.env_file:
        os.environ["PIPELINE_ENV_FILE"] = str(args.env_file.resolve())
    output = (args.output or base / "outputs" / "v3" / "run.csv").resolve()
    os.environ["REPORT_FILE"] = str(output)
    os.environ["PIPELINE_OUTPUT_DIR"] = str(output.parent)
    os.environ["TEST_QUERY_LIMIT"] = str(args.limit)
    os.environ["TEST_MAX_WORKERS"] = str(args.workers)
    os.environ["RETRY_ERRORS_IN_PLACE"] = "1" if args.retry_errors_in_place else "0"
    os.environ['RETRY_INCLUDE_PENDING'] = '1' if args.include_pending else '0'
    if args.retry_errors_in_place:
        os.environ["RETRY_QUERY_SPEC_ERRORS_ONLY"] = "0"
        os.environ["TEST_QUERY_OFFSET"] = "0"
    if args.query_delay is not None:
        os.environ["QUERY_DELAY_SECONDS"] = str(args.query_delay)
    os.environ["QUERY_UNDERSTANDING"] = "1" if args.query_understanding == "on" else "0"
    os.environ["CONTRACT_CHECKS"] = "1" if args.contract_checks == "on" else "0"
    os.environ["AGENT_CONSULTATION"] = "1" if args.agent_consultation == "on" else "0"
    if args.knowledge_mode is not None:
        os.environ["DOMAIN_COMPILATION_MODE"] = args.knowledge_mode
    if args.knowledge_cache is not None:
        os.environ["KNOWLEDGE_CACHE_FILE"] = str(args.knowledge_cache.resolve())
    # Explicit CLI settings win over settings in a selected credential file.
    os.environ["PIPELINE_ENV_OVERRIDE"] = "0"
    if args.check_inputs or args.prepare_knowledge:
        status = "failed"
        mode = "prepare" if args.prepare_knowledge else "check"
        timing_path = base / ".runtime" / "logs" / f"{mode}_{time.time_ns()}_{os.getpid()}.timing.json"
        if args.prepare_knowledge:
            timing.enable_output_records(base / "pipelien_output_sql_v3" / "_preparation" / "_telemetry",
                                         mode="prepare", inputs=selected_inputs)
        try:
            with timing.stage("configuration_and_imports"):
                if args.prepare_knowledge:
                    from run_pipeline_v3_sql.common import load_local_env_file
                    load_local_env_file()
                from run_pipeline_v3_sql.knowledge import load_documents, annotate_schema, compile_knowledge
                from run_pipeline_v3_sql.sql_metadata import load_yaml_metadata
            with timing.stage("schema_and_documents"):
                documents = load_documents(selected_inputs["DOMAIN_INTRO_FILE"],
                                           selected_inputs["BUSINESS_RULES_FILE"],
                                           selected_inputs["TABLE_METADATA_DIR"])
                schema = load_yaml_metadata(selected_inputs["TABLE_METADATA_DIR"], backend="duckdb" if str(args.db).lower().endswith(".duckdb") else "sqlite")
                annotated = annotate_schema(schema, documents)
            print(f"Validated {len(documents)} documents, {len(schema)} tables, "
                  f"{sum('documentation_source' in t for t in annotated.values())} YAML table matches.")
            if args.prepare_knowledge:
                from run_pipeline_v3_sql.common import GPT_OSS_MODEL, KNOWLEDGE_CACHE_DIR
                from run_pipeline_v3_sql.clients import build_gpt_oss_client
                from run_pipeline_v3_sql.knowledge import digest
                from run_pipeline_v3_sql.knowledge_coverage import coverage_report
                client = None
                if not os.getenv("KNOWLEDGE_CACHE_FILE", "").strip():
                    with timing.stage("client_setup"):
                        client = timing.client(build_gpt_oss_client())
                knowledge_status = {}
                with timing.stage("Domain"):
                    pack, identity = compile_knowledge(documents, schema, client, GPT_OSS_MODEL, KNOWLEDGE_CACHE_DIR,
                                                       diagnostics=knowledge_status)
                timing.metadata.update(knowledge_cache_hit=knowledge_status["cache_hit"], knowledge_identity=identity,
                                       knowledge_compilation_mode=knowledge_status["compilation_mode"])
                report = coverage_report(pack, documents, identity, digest(pack))
                print(f"[CACHE] Knowledge {'hit' if knowledge_status['cache_hit'] else 'compiled'}")
                print(f"Compiled {len(pack['rules'])} rules. Identity: {identity}")
                if report.get("coverage_checked") is False:
                    print("Section coverage is not enforced in simple mode.")
                    print(f"Completeness review: {report.get('review_status', 'not_run')}")
                else:
                    print(f"Coverage: {report['section_count']} sections, {len(report['excluded_sections'])} exclusions.")
                if report["excluded_sections"]:
                    print(f"Exclusions recorded in {Path(KNOWLEDGE_CACHE_DIR) / (identity + '.coverage.json')}; no approval required.")
            status = "completed"
        finally:
            timing.save(timing_path, status)
            print(timing.summary())
            print(f"[TIMING] {timing_path}")
        raise SystemExit(0)
    from run_pipeline_v3_sql.runtime_guard import launch as main
    main(timing=timing)

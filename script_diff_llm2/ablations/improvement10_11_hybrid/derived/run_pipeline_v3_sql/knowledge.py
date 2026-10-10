"""Load approved documents and compile a cited, cached domain rule catalogue."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import yaml
from .knowledge_coverage import source_sections, validate_coverage, coverage_report
from .knowledge_progress import KnowledgeProgress

COMPILER_VERSION = "document-rules-v3-chunks"
BENCHMARK_ID = re.compile(r"\b(?:MC|SQA|TT|WM|EC|ARC|BSQ|RC)(?:125)?-(?:\dT-)?\d+\b")
PRIVATE_TEXT = re.compile(r"(?:[A-Za-z]:[\\/]|(?:api[_ -]?key|password|secret_access_key)\s*[:=])", re.I)


def validate_documents(documents):
    """Check usable document structure without filtering supplied content."""
    for document in documents:
        if not isinstance(document.get("content"), str) or not document["content"].strip():
            raise ValueError(f"Empty knowledge source: {document.get('id', 'unknown')}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _write_json_atomic(path, value):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        temporary = handle.name
    os.replace(temporary, path)


def physical_schema(schema):
    allowed = ("name", "backend", "sql_table", "columns", "primary_keys", "unique_keys", "foreign_keys", "ddl", "class_iri", "subject_field", "property_iris", "source_tables")
    column_keys = ("name", "source_column", "sqlite_type", "datatype", "nullable", "predicate_iri", "property_iri", "rdf_predicate")
    result = {}
    for table, details in schema.items():
        result[table] = {key: deepcopy(details[key]) for key in allowed if key in details}
        result[table]["columns"] = [{key: c[key] for key in column_keys if key in c}
                                     for c in details.get("columns", [])]
    return result


def planning_schema(schema):
    """Allow only schema declarations and documented YAML meanings in planning."""
    table_keys = {"name", "backend", "sql_table", "subject_field", "columns", "primary_keys",
                  "unique_keys", "foreign_keys", "ddl", "description", "derived_metrics", "documentation_source", "yaml_metadata", "class_iri", "property_iris", "source_tables", "ontology_metadata", "label_field", "business_purpose", "usage_note"}
    column_keys = {"name", "source_column", "sqlite_type", "datatype", "nullable",
                   "description", "synonyms", "allowed_values", "sample_values",
                   "predicate_iri", "rdf_datatypes", "target_classes", "ontology_attribute",
                   "filterable", "aggregatable", "searchable"}
    result = {}
    for table, details in schema.items():
        result[table] = {key: deepcopy(value) for key, value in details.items()
                         if key in table_keys and key != "columns"}
        result[table]["columns"] = [
            {key: deepcopy(value) for key, value in column.items() if key in column_keys}
            if isinstance(column, dict) else column for column in details.get("columns", [])]
    return result


def load_documents(domain_file, rules_file, yaml_dir):
    documents = []
    paths = [("domain", Path(domain_file)), ("rules", Path(rules_file))]
    yaml_paths = sorted(set(Path(yaml_dir).glob("*.yaml")) | set(Path(yaml_dir).glob("*.yml")))
    if not yaml_paths:
        raise ValueError("No YAML documentation files found.")
    paths += [("yaml/" + path.name, path) for path in yaml_paths]
    for source_id, path in paths:
        content = path.read_text(encoding="utf-8-sig")
        if not content.strip():
            raise ValueError(f"Empty knowledge source: {source_id}")
        record = {"id": source_id, "content": content}
        if source_id.startswith("yaml/"):
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict) or not isinstance(parsed.get("identity"), dict):
                raise ValueError(f"Invalid table YAML: {source_id}")
            record["parsed"] = parsed
        documents.append(record)
    validate_documents(documents)
    return documents


def annotate_schema(schema, documents):
    result = deepcopy(schema)
    used = set()
    for doc in documents:
        metadata = doc.get("parsed")
        if not metadata:
            continue
        table = metadata["identity"].get("id")
        if table not in result:
            continue
        if table in used:
            raise ValueError(f"Duplicate documentation for table {table}")
        used.add(table)
        details = result[table]
        details["documentation_source"] = doc["id"]
        details["yaml_metadata"] = deepcopy(metadata)
        details["description"] = metadata["identity"].get("description", "")
        attrs = {a["name"]: a for a in metadata.get("attributes", [])}
        for column in details["columns"]:
            attr = attrs.get(column["name"], {})
            for key in ("description", "synonyms", "allowed_values", "sample_values"):
                if key in attr:
                    column[key] = deepcopy(attr[key])
        details["derived_metrics"] = deepcopy(metadata.get("derived_attributes", []))
    return result


def validate_field(ref, schema):
    if not isinstance(ref, dict) or set(ref) != {"table", "column"}:
        raise ValueError("Expected a table/column reference.")
    table, column = ref["table"], ref["column"]
    if table not in schema or column not in {c["name"] for c in schema[table]["columns"]}:
        raise ValueError(f"Unknown schema reference: {table}.{column}")


def validate_pack(pack, documents, schema, require_coverage=True, *, sections=None, allow_empty=False):
    keys = {"rules", "conflicts", "source_review"}
    if require_coverage:
        keys.add("coverage")
    if not isinstance(pack, dict) or set(pack) != keys:
        raise ValueError("Rule pack must contain exactly: " + ", ".join(sorted(keys)))
    if not isinstance(pack["conflicts"], list):
        raise ValueError("Conflicts must be a list.")
    if pack["conflicts"]:
        raise ValueError("Knowledge documents have unresolved conflicts: " + json.dumps(pack["conflicts"], ensure_ascii=True)[:3000])
    if not isinstance(pack["rules"], list) or (not pack["rules"] and not allow_empty):
        raise ValueError("Compiler returned no rules.")
    sources = {d["id"]: d["content"] for d in documents}
    review = pack["source_review"]
    if not isinstance(review, dict) or set(review) != set(sources) or any(v != "reviewed" for v in review.values()):
        raise ValueError("Compiler must review every supplied source.")
    ids = set()
    for rule in pack["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"id", "text", "citations", "fields"}:
            raise ValueError("Invalid rule shape.")
        if not isinstance(rule["id"], str) or not re.fullmatch(r"K\d+", rule["id"]) or rule["id"] in ids:
            raise ValueError("Rule IDs must be unique K<number> identifiers.")
        ids.add(rule["id"])
        if not isinstance(rule["text"], str) or not rule["text"].strip():
            raise ValueError("Empty rule text.")
        if not isinstance(rule["citations"], list) or not rule["citations"]:
            raise ValueError("Every rule needs source evidence.")
        quotes = []
        for citation in rule["citations"]:
            if not isinstance(citation, dict) or set(citation) != {"source", "quote"}:
                raise ValueError("Invalid citation.")
            quote = citation["quote"]
            if not isinstance(quote, str) or not quote.strip() or quote not in sources.get(citation["source"], ""):
                raise ValueError("Rule citation does not match supplied document.")
            quotes.append(quote)
        if rule["text"] != "\n".join(quotes):
            raise ValueError("Rule text must exactly concatenate its cited excerpts.")
        if not isinstance(rule["fields"], list):
            raise ValueError("Rule fields must be a list.")
        for ref in rule["fields"]:
            validate_field(ref, schema)
    if require_coverage:
        validate_coverage(pack, documents, sections=sections)
    return pack


def compile_knowledge(documents, schema, client, model, cache_dir, *, diagnostics=None):
    validate_documents(documents)
    from .knowledge_chunks import compile_chunks, chunk_settings
    from .knowledge_single import compile_single, normalize_simple_pack
    mode = os.getenv("DOMAIN_COMPILATION_MODE", "simple").strip().lower()
    if mode not in {"simple", "improvement7", "chunked"}:
        raise ValueError("DOMAIN_COMPILATION_MODE must be simple, improvement7 or chunked.")
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(compilation_mode=mode, cache_hit=False)
    validator = normalize_simple_pack if mode == "simple" else validate_pack
    schema = physical_schema(schema)
    inputs = [{"id": d["id"], "content": d["content"]} for d in documents]
    selected_file = os.getenv("KNOWLEDGE_CACHE_FILE", "").strip()
    if selected_file:
        selected = Path(selected_file).expanduser().resolve()
        package = Path(__file__).resolve().parent
        if selected == package or package in selected.parents:
            raise ValueError("Selected knowledge cache must be outside run_pipeline_v3_sql.")
        saved = json.loads(selected.read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or saved.get("pack_hash") != digest(saved.get("pack")):
            raise ValueError("Invalid selected knowledge cache hash.")
        pack = validator(saved["pack"], documents, schema)
        if digest(pack) != saved["pack_hash"]:
            raise ValueError("Selected cache is incompatible with current documents/schema; regenerate it.")
        binding = {"pack_hash": saved["pack_hash"],
                   "input_hash": digest({"documents": inputs, "schema": schema, "model": model})}
        binding_path = selected.with_name(selected.name + ".inputs.json")
        if binding_path.is_file():
            if json.loads(binding_path.read_text(encoding="utf-8")) != binding:
                raise ValueError("Selected cache inputs or model changed since selection; prepare a fresh cache.")
        else:
            # Explicit file selection authorizes this test's knowledge. Record
            # its input binding so later document/schema changes cannot reuse it.
            _write_json_atomic(binding_path, binding)
        identity = digest({"selected_cache": saved.get("identity"), **binding, "mode": mode})
        print(f"[CACHE] Selected saved knowledge: {selected} ({len(pack['rules'])} rules)", flush=True)
        diagnostics["cache_hit"] = True
        return pack, identity
    compiler_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    coverage_hash = hashlib.sha256(Path(__file__).with_name("knowledge_coverage.py").read_bytes()).hexdigest()
    response_parser_hash = hashlib.sha256(Path(__file__).with_name("knowledge_progress.py").read_bytes()).hexdigest()
    chunks_hash = hashlib.sha256(Path(__file__).with_name("knowledge_chunks.py").read_bytes()).hexdigest()
    units_hash = hashlib.sha256(Path(__file__).with_name("knowledge_units.py").read_bytes()).hexdigest()
    single_hash = hashlib.sha256(Path(__file__).with_name("knowledge_single.py").read_bytes()).hexdigest()
    settings = chunk_settings()
    identity = digest({"version": COMPILER_VERSION, "compiler_hash": compiler_hash,
                       "coverage_hash": coverage_hash, "response_parser_hash": response_parser_hash,
                       "chunks_hash": chunks_hash, "units_hash": units_hash, "single_hash": single_hash,
                       "compilation_mode": mode, "settings": settings,
                       "documents": inputs, "schema": schema, "model": model})
    path = Path(cache_dir) / (identity + ".json")
    if path.is_file():
        cached = json.loads(path.read_text(encoding="utf-8"))
        pack = validator(cached["pack"], documents, schema)
        if cached.get("identity") != identity or cached.get("pack_hash") != digest(pack):
            raise ValueError("Invalid knowledge cache identity.")
        report = coverage_report(pack, documents, identity, digest(pack))
        _write_json_atomic(path.with_name(identity + ".coverage.json"), report)
        diagnostics["cache_hit"] = True
        return pack, identity
    if client is None:
        raise ValueError("No knowledge cache exists for the current inputs; run --prepare-knowledge first.")
    progress = KnowledgeProgress(cache_dir)
    progress.emit("start", f"Cache miss. Mode: {mode}. Model: {model}. Live log: {progress.path}",
                  model=model, compilation_mode=mode, document_count=len(documents), identity=identity)
    if mode in {"simple", "improvement7"}:
        pack = compile_single(documents, schema, client, model, progress, settings, simple=mode == "simple")
    else:
        pack = compile_chunks(documents, schema, client, model, cache_dir, identity,
                              progress, settings)
    validator(pack, documents, schema)
    if pack.get("validation_notes"):
        progress.emit("advisories", f"{len(pack['validation_notes'])} optional metadata issues recorded in the cache; "
                      "rule text retained.", count=len(pack["validation_notes"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(path, {"identity": identity, "pack_hash": digest(pack), "pack": pack})
    report = coverage_report(pack, documents, identity, digest(pack))
    review_path = path.with_name(identity + ".coverage.json")
    _write_json_atomic(review_path, report)
    progress.emit("saved", f"Cache saved: {path}", rule_count=len(pack["rules"]))
    return pack, identity


def prompt_pack(pack):
    result = {"rules": [{"id": r["id"], "text": r["text"], "fields": r["fields"]} for r in pack["rules"]]}
    for source_rule, prompt_rule in zip(pack["rules"], result["rules"]):
        if source_rule.get("sources"):
            prompt_rule["sources"] = deepcopy(source_rule["sources"])
    if pack.get("conflicts"):
        result["conflicts"] = deepcopy(pack["conflicts"])
    return result

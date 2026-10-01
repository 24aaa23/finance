"""Scan operator: executes SPARQL and returns rows."""

from ..common import (
    Any,
    Dict,
    FUSEKI_ENDPOINT,
    FUSEKI_SCAN_TIMEOUT_SECONDS,
    INSTANCE_FILE,
    SPARQL_SCAN_PROCESS_START_METHOD,
    multiprocessing,
    queue,
    rdflib,
    re,
    time,
)
from ..utils import repair_sparql_query, validate_sparql_terms
from .fuseki import execute_sparql_on_fuseki


def _sparql_query_worker(instance_file: str, sparql_query: str, result_queue: Any) -> None:
    """Run rdflib query work in a killable process."""
    try:
        rdf_graph = rdflib.Graph()
        rdf_graph.parse(instance_file, format="turtle")
        results = rdf_graph.query(sparql_query)
        data = []
        for row in results:
            row_dict = {str(var): (None if val is None else str(val)) for var, val in zip(results.vars, row)}
            data.append(row_dict)

        result_queue.put({
            "status": "success",
            "data": data,
            "row_count": len(data),
            "sparql": sparql_query
        })
    except Exception as e:
        result_queue.put({
            "status": "error",
            "error_message": str(e),
            "failed_sparql": sparql_query
        })


def execute_sparql_with_timeout(
    rdf_graph: rdflib.Graph,
    sparql_query: str,
    timeout_seconds: float,
    instance_file: str = INSTANCE_FILE,
) -> Dict[str, Any]:
    """
    Execute SPARQL in a subprocess so a stuck rdflib query can be terminated.
    Python threads cannot safely interrupt a CPU-bound or blocked graph query.
    """
    if timeout_seconds <= 0:
        try:
            results = rdf_graph.query(sparql_query)
            data = []
            for row in results:
                row_dict = {str(var): (None if val is None else str(val)) for var, val in zip(results.vars, row)}
                data.append(row_dict)
            return {
                "status": "success",
                "data": data,
                "row_count": len(data),
                "sparql": sparql_query
            }
        except Exception as e:
            return {
                "status": "error",
                "error_message": str(e),
                "failed_sparql": sparql_query
            }

    try:
        ctx = multiprocessing.get_context(SPARQL_SCAN_PROCESS_START_METHOD)
    except ValueError:
        ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=_sparql_query_worker,
        args=(instance_file, sparql_query, result_queue),
    )
    process.daemon = True
    process.start()

    deadline = time.monotonic() + timeout_seconds
    while process.is_alive():
        try:
            result = result_queue.get_nowait()
            process.join(timeout=1)
            return result
        except queue.Empty:
            pass

        if time.monotonic() >= deadline:
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            return {
                "status": "error",
                "error_message": f"SPARQL execution timed out after {timeout_seconds:g} seconds.",
                "failed_sparql": sparql_query,
                "timeout_seconds": timeout_seconds,
            }

        time.sleep(0.05)

    try:
        return result_queue.get(timeout=1)
    except queue.Empty:
        return {
            "status": "error",
            "error_message": f"SPARQL worker exited without returning a result (exitcode={process.exitcode}).",
            "failed_sparql": sparql_query,
        }


def optimize_missing_related_record_count_sparql(sparql_query: str, rdf_graph: rdflib.Graph) -> str:
    """
    Rewrite a slow but common pattern:
      count distinct base IDs by traversing base -> related, then testing missing related field.

    If the related record itself carries the same base key, scanning the related
    class directly is equivalent for "at least one related record missing X" and
    avoids expensive NOT EXISTS over the base-to-related traversal.
    """
    if rdf_graph is None:
        return sparql_query

    select_match = re.search(
        r"SELECT\s*\(\s*COUNT\s*\(\s*DISTINCT\s+(?P<idvar>\?\w+)\s*\)\s+AS\s+(?P<alias>\?\w+)\s*\)",
        sparql_query,
        flags=re.I,
    )
    if not select_match:
        return sparql_query

    id_var = select_match.group("idvar")
    output_alias = select_match.group("alias")
    base_match = re.search(
        r"(?P<base>\?\w+)\s+rdf:type\s+wm:(?P<base_class>[A-Za-z_][A-Za-z0-9_]*)\s*;\s*"
        r"(?P<base_body>.*?)"
        r"wm:(?P<relationship>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<related>\?\w+)\s*\.",
        sparql_query,
        flags=re.I | re.S,
    )
    if not base_match:
        return sparql_query

    base_body = base_match.group("base_body")
    id_property_match = re.search(
        rf"wm:(?P<id_property>[A-Za-z_][A-Za-z0-9_]*)\s+{re.escape(id_var)}\b",
        base_body,
        flags=re.I,
    )
    if not id_property_match:
        return sparql_query

    related_var = base_match.group("related")
    related_type_match = re.search(
        rf"{re.escape(related_var)}\s+rdf:type\s+wm:(?P<related_class>[A-Za-z_][A-Za-z0-9_]*)\s*\.",
        sparql_query,
        flags=re.I,
    )
    missing_match = re.search(
        rf"FILTER\s+NOT\s+EXISTS\s*\{{\s*{re.escape(related_var)}\s+wm:(?P<missing_property>[A-Za-z_][A-Za-z0-9_]*)\s+\?\w+\s*\.\s*\}}",
        sparql_query,
        flags=re.I | re.S,
    )
    if not related_type_match or not missing_match:
        return sparql_query

    WM = rdflib.Namespace("https://wealth.example.org/ontology/")
    related_class_uri = WM[related_type_match.group("related_class")]
    id_property_uri = WM[id_property_match.group("id_property")]
    has_direct_key = any(
        any(True for _ in rdf_graph.objects(subject=subject, predicate=id_property_uri))
        for subject in rdf_graph.subjects(rdflib.RDF.type, related_class_uri)
    )
    if not has_direct_key:
        return sparql_query

    related_subject = related_var
    id_property = id_property_match.group("id_property")
    missing_property = missing_match.group("missing_property")
    related_class = related_type_match.group("related_class")

    optimized = f"""
PREFIX wm: <https://wealth.example.org/ontology/>
PREFIX kg: <https://wealth.example.org/kg/>
PREFIX wmmeta: <https://wealth.example.org/metadata/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema1: <http://schema.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT (COUNT(DISTINCT {id_var}) AS {output_alias})
WHERE {{
  {related_subject} rdf:type wm:{related_class} ;
                   wm:{id_property} {id_var} .
  FILTER NOT EXISTS {{ {related_subject} wm:{missing_property} ?missingValue . }}
}}
"""
    print("[SYSTEM] Optimized missing-related-record count SPARQL to scan the related class directly.")
    return optimized.strip()


def pre_programmed_scan(inputs: Dict[str, Any], rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    """
    Operator: Scan
    Purpose: Executes the LLM-generated SPARQL query deterministically against
             the RDF Knowledge Graph and parses the output.
    Inputs: 'sparql'
    Outputs: 'data' (List of Dicts), 'row_count'
    """
    sparql_query = repair_sparql_query(inputs.get("sparql", ""))
    if inputs.get("query_spec", {}).get("execution_strategy") != "raw_retrieval_only":
        sparql_query = optimize_missing_related_record_count_sparql(sparql_query, rdf_graph)
    print(f"\n[DEBUG SPARQL EXECUTED]\n{sparql_query}\n")
    if not sparql_query:
        return {"status": "error", "error_message": "No SPARQL provided to Scan operator."}

    term_check = validate_sparql_terms(sparql_query, rdf_graph)
    if not term_check["is_valid"]:
        return {
            "status": "error",
            "error_message": "SPARQL uses terms that do not exist in the RDF graph.",
            "failed_sparql": sparql_query,
            "unknown_terms": term_check["unknown_terms"],
            "term_suggestions": term_check["suggestions"],
        }

    try:
        return execute_sparql_on_fuseki(
            sparql_query,
            FUSEKI_ENDPOINT,
            FUSEKI_SCAN_TIMEOUT_SECONDS,
        )
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "failed_sparql": sparql_query
        }

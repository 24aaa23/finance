import os
import re
import json
import time
import queue
import rdflib
import multiprocessing
import concurrent.futures
from typing import Dict, Any, List
from code.config import SPARQL_SCAN_TIMEOUT_SECONDS, SPARQL_SCAN_MAX_RETRIES, SPARQL_SCAN_PROCESS_START_METHOD, INSTANCE_FILE
from code.kg.alias import normalize_compact_kg_ids

def _sparql_query_worker(instance_file: str, sparql_query: str, result_queue: Any) -> None:
    """Run rdflib query work in a killable process."""
    try:
        rdf_graph = rdflib.Graph()
        rdf_graph.parse(instance_file, format="turtle")
        results = rdf_graph.query(sparql_query)
        data = []
        for row in results:
            row_dict = {str(var): str(val) for var, val in zip(results.vars, row)}
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
                row_dict = {str(var): str(val) for var, val in zip(results.vars, row)}
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

def pre_programmed_scan(inputs: Dict[str, Any], rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    """
    Operator: Scan
    Purpose: Executes the LLM-generated SPARQL query deterministically against
             the RDF Knowledge Graph and parses the output.
    Inputs: 'sparql'
    Outputs: 'data' (List of Dicts), 'row_count'
    """
    sparql_query = repair_sparql_query(inputs.get("sparql", ""))
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
        return execute_sparql_with_timeout(
            rdf_graph,
            sparql_query,
            SPARQL_SCAN_TIMEOUT_SECONDS,
        )
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "failed_sparql": sparql_query
        }

def get_actual_properties_for_failed_query(failed_sparql: str, rdf_graph) -> list:
    """
    Extracts the entity string from a failed SPARQL query, queries the graph
    for that entity, and returns the actual property URIs that exist on it.
    """
    if not rdf_graph:
        return []

    # 1. Extract potential string literals from the failed query (e.g., "INV003" or "INV-003")
    literals = re.findall(r'["\']([^"\']+)["\']', failed_sparql)

    actual_props = set()
    for literal in literals:
        # Skip small/generic strings
        if len(literal) < 3:
            continue

        # 2. Search the physical graph for ANY node that contains this string
        # (Using LCASE to catch "inv003" vs "INV-003" mismatches)
        query = f"""
        SELECT DISTINCT ?p WHERE {{
          ?s ?p ?o .
          FILTER(CONTAINS(LCASE(STR(?o)), "{literal.lower()}"))
        }}
        """
        try:
            for row in rdf_graph.query(query):
                # Clean up the URI to match how the LLM writes prefixes (wm:property)
                prop = str(row[0]).replace("https://wealth.example.org/ontology/", "wm:")
                actual_props.add(prop)
        except Exception:
            continue

        if actual_props:
            break # We found the real properties! Stop searching.

    return list(actual_props)


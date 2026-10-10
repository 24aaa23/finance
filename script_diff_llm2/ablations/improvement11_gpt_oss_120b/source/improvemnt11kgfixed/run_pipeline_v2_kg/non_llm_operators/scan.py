"""Execute raw SPARQL against the configured read-only KG query endpoint."""


def pre_programmed_scan(inputs, endpoint=None):
    from ..common import SPARQL_ENDPOINT, SPARQL_SCAN_TIMEOUT_SECONDS
    from ..kg_backend import execute_sparql
    query = inputs.get("sparql", "")
    print(f"\n[DEBUG SPARQL EXECUTED]\n{query}\n")
    return execute_sparql(query, endpoint or inputs.get("sparql_endpoint", SPARQL_ENDPOINT),
                          SPARQL_SCAN_TIMEOUT_SECONDS)

"""Apache Jena Fuseki helpers."""

from ..common import (
    Any,
    Dict,
    FUSEKI_ENDPOINT,
    FUSEKI_SCAN_TIMEOUT_SECONDS,
    INSTANCE_FILE,
    json,
    socket,
    urllib,
)


def parse_fuseki_sparql_json(payload: Dict[str, Any]) -> list:
    """Convert Fuseki SELECT/ASK JSON responses into the pipeline's row format."""
    if "boolean" in payload:
        return [{"boolean": str(bool(payload.get("boolean"))).lower()}]

    vars_order = payload.get("head", {}).get("vars", [])
    bindings = payload.get("results", {}).get("bindings", [])
    data = []
    for binding in bindings:
        row_dict = {}
        for var in vars_order:
            value = binding.get(var, {})
            if isinstance(value, dict):
                row_dict[str(var)] = str(value["value"]) if "value" in value else None
            else:
                row_dict[str(var)] = None
        data.append(row_dict)
    return data


def execute_sparql_on_fuseki(
    sparql_query: str,
    endpoint: str = FUSEKI_ENDPOINT,
    timeout_seconds: float = FUSEKI_SCAN_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Execute SPARQL through Apache Jena Fuseki and return the existing Scan contract."""
    try:
        request_body = urllib.parse.urlencode({"query": sparql_query}).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=request_body,
            method="POST",
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
        payload = json.loads(response_body)
        data = parse_fuseki_sparql_json(payload)
        return {
            "status": "success",
            "data": data,
            "row_count": len(data),
            "columns": payload.get("head", {}).get("vars", ["boolean"] if "boolean" in payload else []),
            "sparql": sparql_query,
        }
    except socket.timeout:
        return {
            "status": "error",
            "error_message": f"Fuseki SPARQL execution timed out after {timeout_seconds:g} seconds.",
            "failed_sparql": sparql_query,
            "timeout_seconds": timeout_seconds,
        }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "error_message": f"Fuseki HTTP {e.code}: {error_body or str(e)}",
            "failed_sparql": sparql_query,
        }
    except urllib.error.URLError as e:
        return {
            "status": "error",
            "error_message": f"Fuseki connection error: {e.reason}",
            "failed_sparql": sparql_query,
        }
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error_message": f"Fuseki returned non-JSON SPARQL results: {e}",
            "failed_sparql": sparql_query,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "failed_sparql": sparql_query,
        }


def check_fuseki_health(endpoint: str = FUSEKI_ENDPOINT, timeout_seconds: float = 10.0) -> None:
    health_query = """
ASK {
  ?s ?p ?o .
}
"""
    result = execute_sparql_on_fuseki(health_query, endpoint, timeout_seconds)
    if result.get("status") == "success":
        print("[SYSTEM] Fuseki health check passed.")
        return

    raise RuntimeError(
        "Fuseki is not reachable or did not execute the health check. "
        f"Endpoint: {endpoint}. Error: {result.get('error_message')}. "
        "Start Fuseki first, for example: "
        "tools\\apache-jena-fuseki-6.1.0\\fuseki-server.bat --localhost "
        f"--file=\"{INSTANCE_FILE}\" /wealth"
    )

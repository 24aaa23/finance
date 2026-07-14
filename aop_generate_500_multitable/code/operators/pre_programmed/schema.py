import rdflib
from typing import Dict, Any

def pre_programmed_check_schema(inputs: Dict[str, Any], rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    """
    Operator: Schema Validation
    Purpose: Acts as a pre-execution safety check to ensure SPARQL queries
             contain the required prefixes and syntax before execution.
    """
    sparql = inputs.get("sparql", "")
    issues = []

    if "PREFIX wm: <https://wealth.example.org/ontology/>" not in sparql:
         issues.append("Missing the required 'wm:' prefix.")

    #Check for basic SPARQL keywords
    if "SELECT" not in sparql.upper() and "ASK" not in sparql.upper():
         issues.append("Query does not contain a SELECT or ASK statement.")

    if issues:
        return {"is_valid": False, "schema_errors": issues}
    return {"is_valid": True, "sparql_to_execute": sparql}


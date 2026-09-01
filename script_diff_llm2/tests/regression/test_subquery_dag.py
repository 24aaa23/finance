"""
Regression tests for the subquery DAG architecture.
Run with: python3 -m unittest tests.regression.test_subquery_dag -v
"""
import collections
import json
import os
import sys
import types
import unittest


class SimpleDAG:
    def __init__(self):
        self._nodes = {}
        self._edges = []
        self._succs = collections.defaultdict(list)
        self._preds = collections.defaultdict(list)

    def add_node(self, nid, **attrs):
        self._nodes[nid] = {"id": nid, **attrs}

    def add_edge(self, src, dst, **meta):
        self._edges.append((src, dst, meta))
        self._succs[src].append(dst)
        self._preds[dst].append(src)

    @property
    def nodes(self):
        return self._nodes

    def predecessors(self, nid):
        return self._preds[nid]

    def topological_sort(self):
        in_deg = {n: len(self._preds[n]) for n in self._nodes}
        queue = collections.deque(n for n, degree in in_deg.items() if degree == 0)
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for succ in self._succs[node]:
                in_deg[succ] -= 1
                if in_deg[succ] == 0:
                    queue.append(succ)
        if len(order) != len(self._nodes):
            raise RuntimeError("DAG has cycles")
        return order

    def is_dag(self):
        try:
            self.topological_sort()
            return True
        except RuntimeError:
            return False


sql_stub = types.ModuleType("sql_pipeline")


def _gen_sql(inputs, client, model):
    return {"sql": f"SELECT 1 -- {inputs.get('query', '')}", "reasoning": "stub"}


def _psv_sql(inputs, client, model):
    return {"pre_scan_validation": {"is_valid": True, "severity": "valid", "reason": "ok"}}


def _scan_sql(inputs, db_path=":memory:"):
    return {"status": "success", "row_count": 2, "data": [{"id": "P1"}, {"id": "P2"}], "error_message": ""}


sql_stub.semantic_generate_sql = _gen_sql
sql_stub.semantic_pre_scan_validate_sql = _psv_sql
sql_stub.pre_programmed_scan_sql = _scan_sql
sys.modules["sql_pipeline"] = sql_stub


PRE_SCAN_MAX = 2
SCAN_MAX = 2


def make_registry():
    return {
        "_generate_model": "stub",
        "Retrieve": lambda i: {"retrieved_tables": ["StubClass"]},
        "Query_Spec": lambda i: {"query_spec": {"intent": "stub"}},
        "Generate": lambda i: {"sparql": "SELECT ?x WHERE {?x a :S}"},
        "Pre_Scan_Validate": lambda i: {"pre_scan_validation": {"is_valid": True, "severity": "valid", "reason": "ok"}},
        "Scan": lambda i: {"status": "success", "row_count": 3, "data": [{"entity": "E1"}, {"entity": "E2"}, {"entity": "E3"}]},
        "Refine": lambda i: {"sparql": "SELECT ?x WHERE {?x a :R}"},
        "Explain": lambda i: {"final_answer": f"Found {len(i.get('data', []))} results.", "trace": {}},
    }


class StandaloneExecutor:
    def __init__(self, registry, db_path=":memory:"):
        self.registry = registry
        self.db_path = db_path

    def _resolve_bound(self, node_id, dag, cache):
        node_data = dag.nodes[node_id]
        bound = {}
        for inp in node_data.get("inputs", []):
            src = inp.get("source", "")
            if "." not in src:
                continue
            src_node, src_field = src.split(".", 1)
            upstream = cache.get(src_node, {})
            val = upstream.get(src_field)
            if val is None and isinstance(upstream.get("data"), list):
                vals = [r.get(src_field) for r in upstream["data"] if src_field in r]
                val = vals or None
            if val is not None:
                bound[inp["name"]] = val
        return bound

    def _kg(self, node_id, desc, bound, trace):
        inputs = {"query": desc, "bound_inputs": bound}
        inputs.update(self.registry["Retrieve"](inputs))
        inputs.update(self.registry["Query_Spec"](inputs))
        inputs["sparql"] = self.registry["Generate"](inputs).get("sparql", "")
        for _ in range(PRE_SCAN_MAX):
            chk = self.registry["Pre_Scan_Validate"](inputs).get("pre_scan_validation", {})
            if chk.get("is_valid"):
                break
        scan = {"status": "error", "data": []}
        for _ in range(SCAN_MAX):
            scan = self.registry["Scan"](inputs)
            if scan.get("status") != "error":
                break
        nt = {"generated_sparql": inputs["sparql"], "scan_status": scan.get("status", ""), "self_heal_attempts": 0}
        return {"status": scan.get("status", "success"), "data": scan.get("data", []), "trace": nt}

    def _sql(self, node_id, desc, bound, trace):
        inputs = {"query": desc, "bound_inputs": bound}
        inputs.update(self.registry["Query_Spec"](inputs))
        inputs["sql"] = sql_stub.semantic_generate_sql(inputs, None, "stub").get("sql", "")
        for _ in range(PRE_SCAN_MAX):
            chk = sql_stub.semantic_pre_scan_validate_sql(inputs, None, "stub").get("pre_scan_validation", {})
            if chk.get("is_valid"):
                break
        scan = sql_stub.pre_programmed_scan_sql(inputs, db_path=self.db_path)
        nt = {"generated_sql": inputs["sql"], "scan_status": scan.get("status", ""), "self_heal_attempts": 0}
        if scan.get("status") == "error":
            return {"status": "error", "error_message": scan.get("error_message"), "data": [], "trace": nt}
        return {"status": "success", "data": scan.get("data", []), "trace": nt}

    def _set_op(self, op, pred_results):
        sets = []
        for res in pred_results:
            data = res.get("data", []) if isinstance(res, dict) else []
            if data and isinstance(data[0], dict):
                key = list(data[0].keys())[0]
                sets.append(set(str(r.get(key, "")) for r in data))
            else:
                sets.append(set())
        if not sets:
            return {"status": "success", "data": [], "trace": {}}
        if op == "Set_Intersect":
            result = sets[0].intersection(*sets[1:])
        elif op == "Set_Union":
            result = sets[0].union(*sets[1:])
        else:
            result = sets[0].difference(*sets[1:])
        return {"status": "success", "data": [{"entity_id": v} for v in sorted(result)], "trace": {}}

    def execute_dag(self, dag, query):
        cache, all_traces = {}, {}
        for nid in dag.topological_sort():
            nd = dag.nodes[nid]
            op = nd.get("operator", "Subquery")
            backend = nd.get("backend", "KG")
            desc = nd.get("description", query)
            bound = self._resolve_bound(nid, dag, cache)
            preds = [cache[p] for p in dag.predecessors(nid) if p in cache]
            if op == "Subquery":
                result = self._sql(nid, desc, bound, {}) if backend == "SQL" else self._kg(nid, desc, bound, {})
            elif op in {"Set_Intersect", "Set_Union", "Set_Difference"}:
                result = self._set_op(op, preds)
            else:
                result = self.registry.get(op, lambda i: {})({"query": desc, **bound})
            all_traces[nid] = result.pop("trace", {})
            cache[nid] = result
        last = cache.get(dag.topological_sort()[-1], {})
        final = self.registry["Explain"]({"query": query, "data": last.get("data", [])})
        final["trace"] = {"node_traces": all_traces}
        return final


def build_dag(nodes, edges=None):
    dag = SimpleDAG()
    for node in nodes:
        dag.add_node(node["id"], **node)
    for src, dst, meta in (edges or []):
        dag.add_edge(src, dst, **meta)
    return dag


class Test01SingleSQL(unittest.TestCase):
    def test(self):
        ex = StandaloneExecutor(make_registry())
        dag = build_dag([{"id": "Q1", "operator": "Subquery", "backend": "SQL", "description": "Top 5 portfolios", "inputs": [], "outputs": []}])
        r = ex.execute_dag(dag, "Top 5 portfolios")
        self.assertIn("Found 2 results", r["final_answer"])


class Test02SingleKG(unittest.TestCase):
    def test(self):
        ex = StandaloneExecutor(make_registry())
        dag = build_dag([{"id": "Q1", "operator": "Subquery", "backend": "KG", "description": "Investor neighbors", "inputs": [], "outputs": []}])
        r = ex.execute_dag(dag, "Investor neighbors")
        self.assertIn("Found 3 results", r["final_answer"])


class Test03ParallelUnion(unittest.TestCase):
    def test(self):
        ex = StandaloneExecutor(make_registry())
        dag = build_dag(
            [
                {"id": "Q1", "operator": "Subquery", "backend": "SQL", "description": "SQL", "inputs": [], "outputs": [{"name": "id"}]},
                {"id": "Q2", "operator": "Subquery", "backend": "KG", "description": "KG", "inputs": [], "outputs": [{"name": "entity"}]},
                {"id": "M1", "operator": "Set_Union", "backend": "", "description": "Union", "inputs": [], "outputs": []},
            ],
            [("Q1", "M1", {}), ("Q2", "M1", {})],
        )
        r = ex.execute_dag(dag, "Parallel union")
        self.assertIn("Found 5 results", r["final_answer"])


class Test04DependentSQLToKG(unittest.TestCase):
    def test(self):
        ex = StandaloneExecutor(make_registry())
        dag = build_dag(
            [
                {"id": "Q1", "operator": "Subquery", "backend": "SQL", "description": "Get IDs", "inputs": [], "outputs": [{"name": "id"}]},
                {"id": "Q2", "operator": "Subquery", "backend": "KG", "description": "Investors for IDs", "inputs": [{"name": "portfolio_ids", "source": "Q1.id", "type": "entity_id[]"}], "outputs": []},
            ],
            [("Q1", "Q2", {"field": "portfolio_ids", "source_field": "id"})],
        )
        r = ex.execute_dag(dag, "SQL to KG")
        self.assertIn("Found 3 results", r["final_answer"])


class Test05SetIntersect(unittest.TestCase):
    def test(self):
        registry = make_registry()
        registry["Scan"] = lambda i: {"status": "success", "row_count": 2, "data": [{"entity": "P1"}, {"entity": "E2"}]}
        ex = StandaloneExecutor(registry)
        dag = build_dag(
            [
                {"id": "Q1", "operator": "Subquery", "backend": "SQL", "description": "SQL", "inputs": [], "outputs": []},
                {"id": "Q2", "operator": "Subquery", "backend": "KG", "description": "KG", "inputs": [], "outputs": []},
                {"id": "M1", "operator": "Set_Intersect", "backend": "", "description": "Intersect", "inputs": [], "outputs": []},
            ],
            [("Q1", "M1", {}), ("Q2", "M1", {})],
        )
        r = ex.execute_dag(dag, "Intersect")
        self.assertIn("Found 1 results", r["final_answer"])


class Test06EmptyUpstream(unittest.TestCase):
    def test(self):
        registry = make_registry()
        registry["Scan"] = lambda i: {"status": "success", "row_count": 0, "data": []}
        ex = StandaloneExecutor(registry)
        dag = build_dag(
            [
                {"id": "Q1", "operator": "Subquery", "backend": "KG", "description": "Empty", "inputs": [], "outputs": []},
                {"id": "Q2", "operator": "Set_Union", "backend": "", "description": "Union", "inputs": [], "outputs": []},
            ],
            [("Q1", "Q2", {})],
        )
        r = ex.execute_dag(dag, "Empty")
        self.assertIn("Found 0 results", r["final_answer"])


class Test07SQLScanError(unittest.TestCase):
    def test(self):
        original = sql_stub.pre_programmed_scan_sql
        sql_stub.pre_programmed_scan_sql = lambda inputs, db_path=":memory:": {"status": "error", "error_message": "db fail", "data": []}
        try:
            ex = StandaloneExecutor(make_registry())
            dag = build_dag([{"id": "Q1", "operator": "Subquery", "backend": "SQL", "description": "bad sql", "inputs": [], "outputs": []}])
            r = ex.execute_dag(dag, "bad sql")
            self.assertIn("Found 0 results", r["final_answer"])
        finally:
            sql_stub.pre_programmed_scan_sql = original


class Test08KGScanError(unittest.TestCase):
    def test(self):
        registry = make_registry()
        registry["Scan"] = lambda i: {"status": "error", "error_message": "SPARQL timeout", "data": []}
        ex = StandaloneExecutor(registry)
        dag = build_dag([{"id": "Q1", "operator": "Subquery", "backend": "KG", "description": "bad kg", "inputs": [], "outputs": []}])
        r = ex.execute_dag(dag, "bad kg")
        self.assertIn("Found 0 results", r["final_answer"])


class Test09CyclicDAGFallback(unittest.TestCase):
    def test(self):
        dag = build_dag([{"id": "Q1", "operator": "Subquery", "backend": "KG"}, {"id": "Q2", "operator": "Subquery", "backend": "KG"}], [("Q1", "Q2", {}), ("Q2", "Q1", {})])
        self.assertFalse(dag.is_dag())


class Test10SetDifference(unittest.TestCase):
    def test(self):
        registry = make_registry()
        registry["Scan"] = lambda i: {"status": "success", "row_count": 2, "data": [{"entity": "P1"}, {"entity": "E2"}]}
        ex = StandaloneExecutor(registry)
        dag = build_dag(
            [
                {"id": "Q1", "operator": "Subquery", "backend": "SQL", "description": "SQL", "inputs": [], "outputs": []},
                {"id": "Q2", "operator": "Subquery", "backend": "KG", "description": "KG", "inputs": [], "outputs": []},
                {"id": "M1", "operator": "Set_Difference", "backend": "", "description": "Diff", "inputs": [], "outputs": []},
            ],
            [("Q1", "M1", {}), ("Q2", "M1", {})],
        )
        r = ex.execute_dag(dag, "Difference")
        self.assertIn("Found 1 results", r["final_answer"])


if __name__ == "__main__":
    unittest.main()

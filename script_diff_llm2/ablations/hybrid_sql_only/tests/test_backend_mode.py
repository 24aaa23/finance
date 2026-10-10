import json
from types import SimpleNamespace
from unittest.mock import patch

from script_diff_llm.pipeline.decomposition import semantic_decompose
from script_diff_llm.pipeline.dag.planner import build_subquery_dag, fallback_backend_for_query


def test_hybrid_default_still_routes_lookup_to_kg():
    with patch.dict('os.environ', {'PIPELINE_BACKEND_MODE':'hybrid'}):
        assert fallback_backend_for_query('Show the owner') == 'KG'
        assert fallback_backend_for_query('Count owners') == 'SQL'


def test_sql_only_rejects_kg_plan_without_dropping_question():
    with patch.dict('os.environ', {'PIPELINE_BACKEND_MODE':'sql_only'}):
        query='Show the owner and linked accounts'
        dag=build_subquery_dag(query,[{'id':'Q1','operator':'Subquery','backend':'KG','description':'owner','inputs':[],'outputs':[]}])
        assert len(dag)==1
        assert dag.nodes['Q1']['backend']=='SQL'
        assert dag.nodes['Q1']['description']==query
        assert build_subquery_dag(query,[]).nodes['Q1']['backend']=='SQL'
        missing=[{'id':'Q1','operator':'Subquery','description':query,'inputs':[],'outputs':[]}]
        assert build_subquery_dag(query,missing).nodes['Q1']['backend']=='SQL'


def test_decomposition_sees_sql_only_schema_and_retains_original_question():
    requests=[]
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'nodes':[{'id':'Q1','operator':'Subquery','backend':'SQL','description':'paraphrase','inputs':[],'outputs':[]}]})))])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result=semantic_decompose({'query':'Show owner','schema_context':{'SQL':{'owners':['id']}}},client,'model',lambda text,*_:json.loads(text))
    assert 'Available backends for subqueries: SQL only.' in requests[0]['messages'][0]['content']
    assert result['nodes'][0]['description']=='Show owner'

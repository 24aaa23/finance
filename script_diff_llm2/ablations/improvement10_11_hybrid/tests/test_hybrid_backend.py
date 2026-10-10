import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
SQL=ROOT/'ablations/improvement10_models/source/improvement10'
KG=ROOT/'ablations/improvement11_gpt_oss_120b/source/improvemnt11kgfixed'
sys.path.insert(0,str(BASE/'derived'))
os.environ['ONTOLOGY_FILE']=str(KG/'kg_output_fixed/wealth_management_diverse_schema.ttl')
os.environ['INSTANCE_FILE']=str(KG/'kg_output_fixed/wealth_management_diverse_kg.ttl')
os.environ['HYBRID_RUNTIME_DIR']=str(BASE/'runs/offline_test_runtime')
from run_pipeline_v3_sql import hybrid_backend as h

SCHEMA={'relational_records':{'backend':'sqlite'},'GraphEntity':{'backend':'rdf'}}


def test_routing_respects_physical_source_and_rejects_conflicts():
    assert h.select_backend({'global_schema':SCHEMA,'subquestion':{'source_class':'relational_records','backend':'SQL'}})=='sql'
    assert h.select_backend({'global_schema':SCHEMA,'retrieval_spec':{'class':'GraphEntity'}})=='kg'
    assert h.select_backend({'global_schema':SCHEMA,'query_spec':{'retrieval_specs':[{'class':'GraphEntity'}]}})=='kg'
    with pytest.raises(ValueError):h.select_backend({'global_schema':SCHEMA,'subquestion':{'source_class':'GraphEntity','backend':'SQL'}})
    with pytest.raises(ValueError):h.select_backend({'global_schema':SCHEMA,'query_spec':{'retrieval_specs':[{'class':'GraphEntity'},{'class':'relational_records'}]}})


def test_scan_uses_only_selected_backend():
    with patch.object(h,'_SCHEMA',SCHEMA),patch.object(h,'sql_scan',return_value={'data':[{'id':'a'}]}) as sql,patch.object(h,'kg_scan',return_value={'data':[{'id':'b'}]}) as kg,patch.dict(os.environ,{'SPARQL_ENDPOINT':'http://example.invalid/query'}):
        assert h.scan({'retrieval_spec':{'class':'relational_records'}},'database.db')['data']==[{'id':'a'}]
        sql.assert_called_once();kg.assert_not_called()
        assert h.scan({'retrieval_spec':{'class':'GraphEntity'}},'database.db')['data']==[{'id':'b'}]
        kg.assert_called_once()


def test_planning_keeps_rdf_links_and_identity_metadata():
    from run_pipeline_v3_sql.knowledge import planning_schema
    details={'backend':'rdf','subject_field':'subject_iri','label_field':'rdfs_label',
             'class_iri':'https://example.org/Entity','usage_note':'Keep resource identities distinct.',
             'columns':[{'name':'issuer','predicate_iri':'https://example.org/issuer',
                         'target_classes':['Issuer'],'rdf_datatypes':[],'datatype':'object_reference (points to: Issuer)'}]}
    planned=planning_schema({'Entity':details})['Entity']
    assert planned['columns'][0]['target_classes']==['Issuer']
    assert planned['columns'][0]['predicate_iri']=='https://example.org/issuer'
    assert planned['label_field']=='rdfs_label'
    assert planned['usage_note']==details['usage_note']


def test_native_sql_and_rdf_compilers_keep_raw_fields():
    schema={'T':{'backend':'sqlite','sql_table':'T','columns':[{'name':'id','source_column':'id','datatype':'categorical_string'}]},
            'Entity':{'backend':'rdf','class_iri':'https://example.org/Entity','subject_field':'subject_iri',
                      'columns':[{'name':'id','predicate_iri':'https://example.org/id','datatype':'categorical_string'}],
                      'property_iris':{'id':'https://example.org/id'}}}
    h._SCHEMA=schema
    spec={'class':'T','fields':['id'],'filters':[],'optional_fields':[]}
    sql=h.dispatch('Generate',{'global_schema':schema,'retrieval_spec':spec})['sparql']
    assert 'SELECT' in sql.upper() and 'T' in sql
    kg=h.dispatch('Generate',{'global_schema':schema,'retrieval_spec':{'class':'Entity','fields':['subject_iri','id'],'filters':[],'optional_fields':[]}})['sparql']
    assert 'https://example.org/Entity' in kg
    assert 'https://example.org/id' in kg


def test_sql_and_kg_rows_join_in_original_final_spec_runtime(tmp_path):
    import sqlite3
    import rdflib
    from run_pipeline_v3_sql.execution import execute_spec,execution_errors
    from run_pipeline_v3_sql.relational import integrate
    db=tmp_path/'example.db'
    with sqlite3.connect(db) as connection:
        connection.execute('create table facts(id text, amount integer)')
        connection.execute('insert into facts values (?,?)',('E1',7))
    schema={'facts':{'backend':'sqlite','sql_table':'facts','columns':[{'name':'id','source_column':'id','datatype':'categorical_string'},{'name':'amount','source_column':'amount','datatype':'numeric'}]},
            'Entity':{'backend':'rdf','class_iri':'https://example.org/Entity','subject_field':'subject_iri',
                      'columns':[{'name':'id','predicate_iri':'https://example.org/id','datatype':'categorical_string'}, {'name':'sector','predicate_iri':'https://example.org/sector','datatype':'categorical_string'}],
                      'property_iris':{'id':'https://example.org/id','sector':'https://example.org/sector'}}}
    graph=rdflib.Graph().parse(data='@prefix ex: <https://example.org/> . ex:e1 a ex:Entity; ex:id "E1"; ex:sector "A" .',format='turtle')
    sql_inputs={'global_schema':schema,'retrieval_spec':{'class':'facts','fields':['id','amount'],'filters':[],'optional_fields':[]}}
    kg_inputs={'global_schema':schema,'retrieval_spec':{'class':'Entity','fields':['subject_iri','id','sector'],'filters':[],'optional_fields':[]}}
    sql_inputs['sparql']=h.dispatch('Generate',sql_inputs)['sparql']
    kg_inputs['sparql']=h.dispatch('Generate',kg_inputs)['sparql']
    def local_kg(inputs,endpoint):
        data=[{str(k):v.toPython() for k,v in row.asdict().items()} for row in graph.query(inputs['sparql'])]
        return {'status':'success','data':data}
    with patch.object(h,'_SCHEMA',schema),patch.object(h,'kg_scan',side_effect=local_kg),patch.dict(os.environ,{'SPARQL_ENDPOINT':'http://local.fixture/query'}):
        sql_rows=h.scan(sql_inputs,str(db))['data']
        kg_rows=h.scan(kg_inputs,str(db))['data']
    plan={'merge_steps':[{'operator':'Integrate','inputs':['sql','kg'],'join_key':'id','output':'joined'}],
          'projection':['id','amount','sector']}
    result,log=execute_spec(plan,{'sql':sql_rows,'kg':kg_rows},{'Integrate':integrate})
    assert not execution_errors(log)
    assert result==[{'id':'E1','amount':7,'sector':'A'}]

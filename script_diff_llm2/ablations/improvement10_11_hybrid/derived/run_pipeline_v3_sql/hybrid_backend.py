"""Backend routing for a derived SQL+KG Improvement 10/11 pipeline."""
from copy import deepcopy
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from .sql_metadata import load_yaml_metadata
from .knowledge import load_documents as load_sql_documents
from .llm_operators.query_spec import semantic_build_query_spec as sql_spec
from .llm_operators.generate import semantic_generate_sparql as sql_generate
from .llm_operators.pre_scan_validate import semantic_pre_scan_validate as sql_validate
from .llm_operators.refine import semantic_refine as sql_refine
from .non_llm_operators.scan import pre_programmed_scan as sql_scan
from .business_context import configure_business_context as configure_sql_context
from run_pipeline_v2_kg.kg_metadata import load_kg_metadata
from run_pipeline_v2_kg.knowledge import load_documents as load_kg_documents
from run_pipeline_v2_kg.llm_operators.query_spec import semantic_build_query_spec as kg_spec
from run_pipeline_v2_kg.llm_operators.generate import semantic_generate_sparql as kg_generate
from run_pipeline_v2_kg.llm_operators.pre_scan_validate import semantic_pre_scan_validate as kg_validate
from run_pipeline_v2_kg.llm_operators.refine import semantic_refine as kg_refine
from run_pipeline_v2_kg.non_llm_operators.scan import pre_programmed_scan as kg_scan
from run_pipeline_v2_kg.business_context import configure_business_context as configure_kg_context

_SCHEMA={}


def load_hybrid_metadata(yaml_dir):
    global _SCHEMA
    sql=load_yaml_metadata(yaml_dir)
    kg=load_kg_metadata(os.environ['ONTOLOGY_FILE'],os.environ['INSTANCE_FILE'],
                        Path(os.environ['HYBRID_RUNTIME_DIR'])/'kg_metadata')
    collisions=set(sql)&set(kg)
    if collisions:raise ValueError('Ambiguous SQL/KG source names: '+str(sorted(collisions)))
    _SCHEMA={**sql,**kg}
    return deepcopy(_SCHEMA)


def load_hybrid_documents(domain_file,rules_file,yaml_dir):
    sql=load_sql_documents(domain_file,rules_file,yaml_dir)
    ontology=next(d for d in load_kg_documents(domain_file,rules_file,os.environ['ONTOLOGY_FILE']) if d['id']=='ontology')
    if any(d['id']=='ontology' for d in sql):raise ValueError('Duplicate ontology document ID')
    return sql+[ontology]


def configure_context(pack):
    configure_sql_context(pack)
    configure_kg_context(pack)


def get_hybrid_index(metadata):
    return {name:{'backend':{'sqlite':'SQL','rdf':'KG'}[details['backend']],
                  'columns':details.get('columns',[]),
                  'source_tables':details.get('source_tables',[])}
            for name,details in metadata.items()}


def select_backend(inputs):
    """Dispatch by the schema's immutable physical source, never query wording."""
    schema=inputs.get('global_schema') or _SCHEMA
    source=(inputs.get('subquestion') or {}).get('source_class')
    retrieval=inputs.get('retrieval_spec') or {}
    if retrieval.get('class'):source=retrieval['class']
    if not source:
        retrievals=(inputs.get('query_spec') or {}).get('retrieval_specs',[])
        sources={r.get('class') for r in retrievals if isinstance(r,dict)}
        if len(sources)==1:source=next(iter(sources))
    if source not in schema:raise ValueError('No unambiguous schema-backed branch source: '+str(source))
    backend={'sqlite':'sql','rdf':'kg'}.get(schema[source].get('backend'),schema[source].get('backend'))
    if backend not in {'sql','kg'}:raise ValueError('Unsupported backend for '+source)
    declared=(inputs.get('subquestion') or {}).get('backend')
    if declared:
        declared={'sqlite':'sql','rdf':'kg'}.get(str(declared).lower(),str(declared).lower())
        if declared!=backend:raise ValueError('Declared backend conflicts with source schema: '+source)
    return backend


def dispatch(stage,inputs,client=None,model=None):
    backend=select_backend(inputs)
    retrieval=inputs.get('retrieval_spec') or {}
    source=retrieval.get('class') or (inputs.get('subquestion') or {}).get('source_class')
    if not source:
        specs=(inputs.get('query_spec') or {}).get('retrieval_specs',[])
        source=specs[0].get('class') if len(specs)==1 else None
    print(f'[HYBRID] stage={stage} backend={backend.upper()} source={source}',flush=True)
    functions={'Query_Spec':(sql_spec,kg_spec),'Generate':(sql_generate,kg_generate),
               'Pre_Scan_Validate':(sql_validate,kg_validate),'Refine':(sql_refine,kg_refine)}
    result=functions[stage][backend=='kg'](inputs,client,model)
    return result


def scan(inputs,db_path):
    backend=select_backend(inputs)
    return sql_scan(inputs,db_path) if backend=='sql' else kg_scan(inputs,os.environ['SPARQL_ENDPOINT'])

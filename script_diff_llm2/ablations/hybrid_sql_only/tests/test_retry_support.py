import sys
from pathlib import Path
from dataclasses import dataclass
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retry_support import is_transient_failure, filter_resume_state


@dataclass
class State:
    results_list:list
    completed_row_ids:set
    retry_count:int
    resume_enabled:bool


def test_retry_only_transient_failures():
    good={'Sample Row ID':'ok','New Status':'PIPELINE_SUCCESS','Validation Reason':'Earlier 429 warning'}
    semantic={'Sample Row ID':'bad','New Status':'PRE_SCAN_ERROR','Validation Reason':'Missing requested output columns'}
    api={'Sample Row ID':'api','New Status':'DAG_NODE_ERROR','Node Traces':'{"Q1":{"trace":{"error_message":"Error code: 429 - rate_limit_exceeded"}}}'}
    connection={'Sample Row ID':'net','New Status':'PRE_SCAN_ERROR','New Pipeline Result':'ERROR: Connection error.'}
    state=State([good,semantic,api,connection],{'ok','bad','api','net'},0,True)
    updated=filter_resume_state(state)
    assert updated.completed_row_ids=={'ok','bad'}
    assert updated.results_list==[good,semantic]
    assert updated.retry_count==2
    assert len(state.results_list)==4
    assert not is_transient_failure(good)
    assert not is_transient_failure(semantic)


def test_empty_resume_and_non_api_numbers():
    state=State([],set(),0,False)
    assert filter_resume_state(state) is state
    assert not is_transient_failure({'New Status':'PRE_SCAN_ERROR','Validation Reason':'Expected 429 records'})

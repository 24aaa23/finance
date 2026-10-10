#!/usr/bin/env python3
"""Run the main pipeline with ablation-local retry selection; scoring unchanged."""
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
if len(sys.argv)>1:os.environ['EXPERIMENT_CONFIG']=sys.argv[1]
from script_diff_llm.pipeline import core_pipeline
from script_diff_llm.evaluation.reporting import ResumeState
from retry_support import filter_resume_state

original_resume=core_pipeline.load_resume_state


def retry_resume(path,version):
    state=original_resume(path,version)
    if os.getenv('SQL_ONLY_RETRY_API_ERRORS','1')!='1':return state
    updated=filter_resume_state(state)
    count=updated.retry_count-state.retry_count
    if count:print(f'[API RETRY] Retrying {count} saved transient API failures; keeping other rows.',flush=True)
    return updated



core_pipeline.load_resume_state=retry_resume
if __name__=='__main__':core_pipeline.main()

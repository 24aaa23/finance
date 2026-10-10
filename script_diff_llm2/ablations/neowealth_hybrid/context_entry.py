"""Apply documented session settings to this context experiment only."""
from pathlib import Path
import sys
import runpy
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from script_diff_llm.backends import sql_connection
original = sql_connection.connect_readonly

def context_connection(path):
    connection = original(path)
    if sql_connection.is_duckdb(path):
        connection.execute("SET default_null_order='nulls_last_on_asc_first_on_desc'")
        connection.execute("SET default_collation='nocase'")
    return connection

sql_connection.connect_readonly = context_connection
runpy.run_path(str(ROOT / 'runners/train/run_pipeline.py'), run_name='__main__')

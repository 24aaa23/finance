"""Install the connection adapter in this process, then run unchanged source."""
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
PIPELINE = BASE / 'source/improvement10/run_pipeline_v3_sql _'
from bedrock_converse import build_client
import openai

# Install before imports, allowing run.py to resolve CLI paths before common.py
# captures them. The adapter itself retains the original SDK client class.
openai.OpenAI = build_client
runpy.run_path(str(PIPELINE / 'run.py'), run_name='__main__')

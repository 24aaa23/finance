@echo off
setlocal
cd /d "%~dp0"
set "TEST_MAX_WORKERS=1"
set "TEST_QUERY_OFFSET=0"
set "RETRY_QUERY_SPEC_ERRORS_ONLY=0"
python -u -B "%~dp0run_pipeline_v2_kg\prepare_dataset.py"
if errorlevel 1 exit /b 1
if /i "%~1"=="--check" (
    python -u -B "%~dp0run_pipeline_v2_kg\run.py" --env-file "%~dp0.env" --check-inputs
    exit /b
)
if /i "%~1"=="--retry" (
    python -u -B "%~dp0run_pipeline_v2_kg\run.py" --env-file "%~dp0.env" --knowledge-mode simple --questions "%~dp0pipeline_output_kg_v11\input_questions.jsonl" --output "%~dp0pipeline_output_kg_v11\raw_pipeline_v9.csv" --retry-errors-in-place
    exit /b
)
python -u -B "%~dp0run_pipeline_v2_kg\run.py" --env-file "%~dp0.env" --knowledge-mode simple --questions "%~dp0pipeline_output_kg_v11\input_questions.jsonl" --output "%~dp0pipeline_output_kg_v11\raw_pipeline_v9.csv" --limit 0 %*
exit /b %errorlevel%

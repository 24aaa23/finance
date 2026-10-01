@echo off
setlocal

if "%~1"=="" (
    echo Usage: run_one_type.cmd "Benchmark"
    exit /b 2
)

set "EXPERIMENT_DIR=%~dp0"
python "%EXPERIMENT_DIR%run_pipeline_v2\scripts\run_question_types_v2.py" --type "%~1" --workers 1
exit /b %errorlevel%

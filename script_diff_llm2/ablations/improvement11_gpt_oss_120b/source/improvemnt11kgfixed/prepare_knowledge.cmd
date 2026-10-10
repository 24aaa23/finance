@echo off
setlocal
cd /d "%~dp0"
python -u -B "%~dp0run_pipeline_v2_kg\prepare_knowledge.py" --env-file "%~dp0.env"
exit /b %errorlevel%

@echo off
setlocal
cd /d "%~dp0"

where java >nul 2>&1
if errorlevel 1 (
    echo Java was not found. Install Java 21 or make it available in PATH.
    exit /b 1
)
if not exist "%~dp0tools\apache-jena-fuseki-6.1.0\fuseki-server.jar" (
    echo Fuseki is missing from improvemnt11kgfixed\tools\apache-jena-fuseki-6.1.0.
    exit /b 1
)
if not exist "%~dp0kg_output_fixed\wealth_management_diverse_kg.ttl" (
    echo The KG file is missing from improvemnt11kgfixed\kg_output_fixed.
    exit /b 1
)
if /i "%~1"=="--check" (
    echo Ready: Java, local Fuseki and the improvemnt11kgfixed KG file were found.
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_kg.ps1" -ShowLogs
exit /b %errorlevel%

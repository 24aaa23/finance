@echo off
setlocal

set "ROOT=%~dp0"
set "FUSEKI_DIR=%ROOT%tools\apache-jena-fuseki-6.1.0"
set "KG_FILE=%ROOT%kg\wealth_management_diverse_kg.ttl"

if not exist "%FUSEKI_DIR%\fuseki-server.bat" (
  echo Fuseki server was not found at:
  echo %FUSEKI_DIR%\fuseki-server.bat
  exit /b 1
)

if not exist "%KG_FILE%" (
  echo KG file was not found at:
  echo %KG_FILE%
  exit /b 1
)

cd /d "%FUSEKI_DIR%"
call fuseki-server.bat --localhost --file="%KG_FILE%" /wealth

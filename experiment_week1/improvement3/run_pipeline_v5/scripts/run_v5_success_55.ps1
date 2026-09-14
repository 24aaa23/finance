Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = "C:\Users\AMAN KUMAR SINGH\Desktop\financial"
$InputCsv = Join-Path $Root "experiment_week1\improvement3\pipelien_output\v4_latest_success_55.csv"
$OutputDir = Join-Path $Root "experiment_week1\improvement3\pipelien_output"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ReportFile = Join-Path $OutputDir "v5_multistep_contract_success_55_$Stamp.csv"

$env:INPUT_QUERY_CSV = $InputCsv
$env:REPORT_FILE = $ReportFile
$env:PIPELINE_OUTPUT_DIR = $OutputDir
$env:TEST_QUERY_OFFSET = "0"
$env:TEST_QUERY_LIMIT = "0"
$env:TEST_MAX_WORKERS = "1"
$env:GPT_OSS_LLM_GRADER_PIPELINE_VERSION = "aop-improvement3-v5-multistep-contract"

Push-Location $Root
try {
    python experiment_week1/improvement3/run_pipeline_v5/run.py
    Write-Host "V5 report written to: $ReportFile"
    Write-Host "V5 debug report written to: $($ReportFile -replace '\.csv$', '_debug.csv')"
}
finally {
    Pop-Location
}

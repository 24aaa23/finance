param(
    [Parameter(Mandatory = $true)]
    [string]$CsvName,
    [ValidateRange(0, 1000000)]
    [int]$Limit = 0,
    [ValidateRange(0, 1000000)]
    [int]$Offset = 0,
    [ValidateRange(1, 32)]
    [int]$Workers = 1,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pipelineDir = Split-Path -Parent $scriptDir
$experimentDir = Split-Path -Parent $pipelineDir
$datasetDir = Join-Path $experimentDir 'dataset'
$outputDir = Join-Path $experimentDir 'pipeline_output_v2'
$inputPath = Join-Path $datasetDir $CsvName

if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
    throw "Missing dataset CSV: $inputPath"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$stem = [System.IO.Path]::GetFileNameWithoutExtension($CsvName)
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$reportPath = Join-Path $outputDir ("v2_{0}_{1}.csv" -f $stem, $timestamp)
$runPy = Join-Path $pipelineDir 'run.py'

Write-Output "Pipeline: $pipelineDir"
Write-Output "Input:    $inputPath"
Write-Output "Output:   $reportPath"
Write-Output "Limit:    $(if ($Limit -eq 0) { 'all' } else { $Limit })"
Write-Output "Offset:   $Offset"
Write-Output "Workers:  $Workers"

if ($DryRun) {
    return
}

$settings = @{
    INPUT_QUERY_CSV = $inputPath
    TEST_QUERY_LIMIT = [string]$Limit
    TEST_QUERY_OFFSET = [string]$Offset
    TEST_MAX_WORKERS = [string]$Workers
    REPORT_FILE = $reportPath
    PIPELINE_OUTPUT_DIR = $outputDir
    GPT_OSS_LLM_GRADER_PIPELINE_VERSION = 'aop-improvement5-business-rules-v1'
}

$savedSettings = @{}
try {
    foreach ($name in $settings.Keys) {
        $savedSettings[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    python $runPy
    if ($LASTEXITCODE -ne 0) {
        throw "Pipeline exited with code $LASTEXITCODE"
    }
} finally {
    foreach ($name in $savedSettings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedSettings[$name], 'Process')
    }
}


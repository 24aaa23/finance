param(
    [ValidateSet("non_success_part2_68", "non_success_part1_69", "success_55")]
    [string]$Subset = "non_success_part2_68",
    [int]$Limit = 0,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path $PSScriptRoot -Parent
$ExperimentRoot = Split-Path $PackageRoot -Parent
$InputCsv = Join-Path $ExperimentRoot "dataset\v4_input_$Subset.csv"
$OutputDirectory = Join-Path $PackageRoot "outputs"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$ReportFile = Join-Path $OutputDirectory "v8_comparative_${Subset}_$Stamp.csv"
$Launcher = Join-Path $PackageRoot "run.py"
if ($Limit -lt 0) { throw "Limit must be nonnegative; 0 runs the entire subset." }
if (-not (Test-Path -LiteralPath $InputCsv -PathType Leaf)) { throw "Missing input: $InputCsv" }
if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) { throw "Missing V8 launcher: $Launcher" }
if ($DryRun) {
    Write-Output "Package: $PackageRoot"
    Write-Output "Input: $InputCsv"
    Write-Output "Report: $ReportFile"
    Write-Output "Limit: $Limit (0 means all rows)"
    exit 0
}

$Settings = @{
    INPUT_QUERY_CSV = $InputCsv
    REPORT_FILE = $ReportFile
    PIPELINE_OUTPUT_DIR = $OutputDirectory
    TEST_QUERY_OFFSET = "0"
    TEST_QUERY_LIMIT = "$Limit"
    TEST_MAX_WORKERS = "1"
    GPT_OSS_LLM_GRADER_PIPELINE_VERSION = "aop-improvement3-v8-comparative"
}
$PreviousSettings = @{}
try {
    foreach ($Name in $Settings.Keys) {
        $PreviousSettings[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
        [Environment]::SetEnvironmentVariable($Name, $Settings[$Name], "Process")
    }
    & python $Launcher
    if ($LASTEXITCODE -ne 0) { throw "V8 exited with code $LASTEXITCODE" }
    Write-Output "V8 report: $ReportFile"
}
finally {
    foreach ($Name in $PreviousSettings.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousSettings[$Name], "Process")
    }
}

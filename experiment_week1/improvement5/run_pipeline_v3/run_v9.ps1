param(
    [ValidateSet('non_success_part2_68', 'non_success_part1_69', 'success_55')]
    [string]$Subset = 'non_success_part2_68',
    [ValidateRange(1, 1000)][int]$Limit = 68,
    [switch]$DryRun
)
$base = Split-Path -Parent $PSScriptRoot
$inputPath = Join-Path $base "dataset\v4_input_$Subset.csv"
$reportPath = Join-Path $base "pipeline_output_v3\v3_${Subset}_$(Get-Date -Format 'yyyyMMdd_HHmmss_fff').csv"
if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) { throw "Missing input: $inputPath" }
Write-Output "Input: $inputPath"
Write-Output "Report: $reportPath"
if ($DryRun) { return }
$settings = @{
    INPUT_QUERY_CSV = $inputPath
    TEST_QUERY_LIMIT = [string]$Limit
    TEST_QUERY_OFFSET = '0'
    REPORT_FILE = $reportPath
    PIPELINE_OUTPUT_DIR = (Split-Path -Parent $reportPath)
    GPT_OSS_LLM_GRADER_PIPELINE_VERSION = 'aop-improvement5-v3'
    BUSINESS_RULE_PACK_FILE = (Join-Path $PSScriptRoot 'business_rule_pack.json')
    FINAL_SEMANTIC_REVIEW = '1'
    FINAL_SEMANTIC_REPAIR_ATTEMPTS = '1'
}
$savedSettings = @{}
try {
    foreach ($name in $settings.Keys) {
        $savedSettings[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    python (Join-Path $PSScriptRoot 'run.py')
    if ($LASTEXITCODE -ne 0) { throw "Pipeline exited with code $LASTEXITCODE" }
} finally {
    foreach ($name in $savedSettings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedSettings[$name], 'Process')
    }
}

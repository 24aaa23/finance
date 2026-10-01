param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('benchmark', 'at_risk_critical', 'batch_status', 'enrichment_context',
                 'multi_step_comparative', 'reference_compliance', 'scoring_quantitative', 'temporal_transaction')]
    [string]$Type,

    [string]$OutputRoot = (Join-Path $PSScriptRoot 'pipelien_output\run_v5_memory_safe')
)

$ErrorActionPreference = 'Stop'
if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
    $OutputRoot = Join-Path $PSScriptRoot $OutputRoot
}
$typeDir = Join-Path $OutputRoot $Type
$inputPath = Join-Path $typeDir 'raw_pipeline_v9.csv'
if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
    throw "Pipeline report not found: $inputPath"
}
$settings = @{
    PIPELINE_OUTPUT_DIR = $typeDir
    RAW_REPORT_FILE = $inputPath
    GRADED_REPORT_FILE = (Join-Path $typeDir 'graded_final_answers_gpt_5_6_terra.csv')
}
$savedSettings = @{}
try {
    foreach ($name in $settings.Keys) {
        $savedSettings[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    python (Join-Path $PSScriptRoot 'grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py')
    if ($LASTEXITCODE -ne 0) { throw "Grader exited with code $LASTEXITCODE" }
} finally {
    foreach ($name in $savedSettings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedSettings[$name], 'Process')
    }
}

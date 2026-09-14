param(
    [Parameter(Mandatory=$true)][string]$Report,
    [string]$Output = ''
)

$root = Split-Path -Parent $PSScriptRoot
$base = Join-Path $root 'experiment_week1\improvement3'
$reportPath = (Resolve-Path $Report).Path
if (-not $Output) {
    $stem = [IO.Path]::GetFileNameWithoutExtension($reportPath)
    $Output = Join-Path (Split-Path $reportPath) ($stem + '_graded.csv')
}
$env:RAW_REPORT_FILE = $reportPath
$env:GRADED_REPORT_FILE = $Output

python (Join-Path $base 'run_pipeline_v6\grade_final_answers.py')

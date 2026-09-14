param([int]$Limit = 442, [int]$Offset = 0)

$root = Split-Path -Parent $PSScriptRoot
$base = Join-Path $root 'experiment_week1\improvement3'
$env:INPUT_SAMPLE_FILE = Join-Path $base 'dataset\verification_results_v2_sql_correct_442.xlsx'
$env:TEST_QUERY_LIMIT = "$Limit"
$env:TEST_QUERY_OFFSET = "$Offset"
$env:REPORT_FILE = Join-Path $base 'pipelien_output\raw_pipeline_v4_comparison.csv'
$env:GPT_OSS_LLM_GRADER_PIPELINE_VERSION = 'aop-improvement3-v4-comparison'

python (Join-Path $base 'run_pipeline_v4\run.py')

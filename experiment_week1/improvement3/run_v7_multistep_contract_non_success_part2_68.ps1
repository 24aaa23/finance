$base = $PSScriptRoot
$out = Join-Path $base 'pipelien_output'
$env:INPUT_QUERY_CSV = Join-Path $base 'dataset\v4_input_non_success_part2_68.csv'
$env:TEST_QUERY_LIMIT = '68'
$env:TEST_QUERY_OFFSET = '0'
$env:REPORT_FILE = Join-Path $out 'v7_multistep_contract_non_success_part2_68.csv'
$env:GPT_OSS_LLM_GRADER_PIPELINE_VERSION = 'aop-improvement3-v7'
python (Join-Path $base 'run_pipeline_v7\run.py')

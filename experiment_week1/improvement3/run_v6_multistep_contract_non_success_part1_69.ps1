$base = $PSScriptRoot
$out = Join-Path $base 'pipelien_output'
$env:INPUT_QUERY_CSV = Join-Path $base 'dataset\v4_input_non_success_part1_69.csv'
$env:TEST_QUERY_LIMIT = '69'
$env:TEST_QUERY_OFFSET = '0'
$env:REPORT_FILE = Join-Path $out 'v6_multistep_contract_non_success_part1_69.csv'
$env:GPT_OSS_LLM_GRADER_PIPELINE_VERSION = 'aop-improvement3-v6-contract-retrieval'
python (Join-Path $base 'run_pipeline_v6\run.py')

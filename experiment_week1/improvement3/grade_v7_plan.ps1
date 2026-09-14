$base = $PSScriptRoot
$grader = Join-Path $base 'run_pipeline_v7\grade_final_answers.py'
$out = Join-Path $base 'pipelien_output'

$reports = @(
    @{ Input='v7_multistep_contract_success_55.csv'; Output='graded_v7_multistep_contract_success_55.csv' },
    @{ Input='v7_multistep_contract_non_success_part1_69.csv'; Output='graded_v7_multistep_contract_non_success_part1_69.csv' },
    @{ Input='v7_multistep_contract_non_success_part2_68.csv'; Output='graded_v7_multistep_contract_non_success_part2_68.csv' }
)

foreach ($report in $reports) {
    $env:RAW_REPORT_FILE = Join-Path $out $report.Input
    $env:GRADED_REPORT_FILE = Join-Path $out $report.Output
    python $grader
}

param(
    [ValidateRange(0, 1000000)]
    [int]$Limit = 0,
    [ValidateRange(0, 1000000)]
    [int]$Offset = 0,
    [ValidateRange(1, 32)]
    [int]$Workers = 1,
    [switch]$DryRun
)

& (Join-Path $PSScriptRoot 'run_one_dataset_v3.ps1') `
    -CsvName 'final_605_question.csv' `
    -Limit $Limit `
    -Offset $Offset `
    -Workers $Workers `
    -DryRun:$DryRun

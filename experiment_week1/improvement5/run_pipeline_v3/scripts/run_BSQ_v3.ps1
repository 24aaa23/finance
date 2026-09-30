param([int]$Limit = 0, [int]$Offset = 0, [int]$Workers = 1, [switch]$DryRun)
& (Join-Path $PSScriptRoot 'run_one_dataset_v3.ps1') -CsvName 'BSQ.csv' -Limit $Limit -Offset $Offset -Workers $Workers -DryRun:$DryRun

param(
    [ValidateRange(0, 1000000)]
    [int]$Limit = 0,
    [ValidateRange(0, 1000000)]
    [int]$Offset = 0,
    [ValidateRange(1, 32)]
    [int]$Workers = 1,
    [switch]$ContinueOnError,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$csvNames = @(
    'ARC.csv',
    'BSQ.csv',
    'EC.csv',
    'MC.csv',
    'MC_diverse.csv',
    'RC.csv',
    'SQA.csv',
    'TT.csv',
    'WM.csv'
)

$runner = Join-Path $PSScriptRoot 'run_one_dataset_v3.ps1'
$failures = @()

foreach ($csvName in $csvNames) {
    Write-Output ""
    Write-Output "=== Running $csvName ==="
    try {
        & $runner -CsvName $csvName -Limit $Limit -Offset $Offset -Workers $Workers -DryRun:$DryRun
    } catch {
        $failures += [pscustomobject]@{ CsvName = $csvName; Error = $_.Exception.Message }
        Write-Warning "Failed ${csvName}: $($_.Exception.Message)"
        if (-not $ContinueOnError) {
            throw
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Output ""
    Write-Output "Failures:"
    $failures | Format-Table -AutoSize
    exit 1
}

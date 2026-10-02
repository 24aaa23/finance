param(
    [string]$Type,
    [ValidateSet(1)] [int]$Workers = 1,
    [ValidateRange(0, 125)] [int]$Limit = 0,
    [ValidateRange(0, 125)] [int]$Offset = 0,
    [string]$OutputRoot = '',
    [string]$EnvFile = '',
    [switch]$PrepareOnly,
    [switch]$RetryQuerySpecErrors
)

$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'run_question_types_v2.py'
$arguments = @($scriptPath, '--limit', $Limit, '--offset', $Offset)
if ($Type) { $arguments += @('--type', $Type) }
if ($OutputRoot) { $arguments += @('--output-root', $OutputRoot) }
if ($EnvFile) { $arguments += @('--env-file', $EnvFile) }
if ($PrepareOnly) { $arguments += '--prepare-only' }
if ($RetryQuerySpecErrors) { $arguments += '--retry-query-spec-errors' }
python @arguments
if ($LASTEXITCODE -ne 0) { throw "Question-type runner exited with code $LASTEXITCODE" }

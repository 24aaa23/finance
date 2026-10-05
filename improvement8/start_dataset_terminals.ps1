param(
    [ValidateSet('ARC', 'BSQ', 'EC', 'MC', 'RC', 'SQA', 'TT', 'WM')]
    [string]$Type,
    [string]$Python = 'python',
    [string]$KnowledgeCache,
    [string]$OutputRoot,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$experimentRoot = $PSScriptRoot
$runner = Join-Path $experimentRoot 'run_pipeline_v2_sql/run.py'
$envFile = Join-Path $experimentRoot '.env'
$runOutputRoot = Join-Path $experimentRoot 'pipelien_output_sql'
if ($OutputRoot) {
    $runOutputRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputRoot)
}
$groups = @(
    @{ Code = 'ARC'; Folder = 'at_risk_critical' },
    @{ Code = 'BSQ'; Folder = 'batch_status' },
    @{ Code = 'EC'; Folder = 'enrichment_context' },
    @{ Code = 'MC'; Folder = 'multi_step_comparative' },
    @{ Code = 'RC'; Folder = 'reference_compliance' },
    @{ Code = 'SQA'; Folder = 'scoring_quantitative' },
    @{ Code = 'TT'; Folder = 'temporal_transaction' },
    @{ Code = 'WM'; Folder = 'benchmark' }
)
$pythonExe = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Credential file is missing: $envFile"
}

# Keep reports and derived knowledge local even if an older shell exported paths.
$env:KNOWLEDGE_CACHE_DIR = Join-Path $experimentRoot '.runtime/knowledge'
$env:DOMAIN_COMPILATION_MODE = 'simple'
if ($KnowledgeCache) {
    $selectedKnowledge = (Resolve-Path -LiteralPath $KnowledgeCache -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $selectedKnowledge -PathType Leaf)) { throw 'KnowledgeCache must be a saved JSON file.' }
    $env:KNOWLEDGE_CACHE_FILE = $selectedKnowledge
}
$env:TEST_MAX_WORKERS = '1'
$env:TEST_QUERY_OFFSET = '0'
$env:RETRY_QUERY_SPEC_ERRORS_ONLY = '0'
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'

if ($Type) {
    $group = $groups | Where-Object { $_.Code -eq $Type }
    $typeOutput = Join-Path $runOutputRoot $group.Folder
    New-Item -ItemType Directory -Path $typeOutput -Force | Out-Null
    $questions = Join-Path $experimentRoot "dataset/$Type.csv"
    # Retain the input manifest expected by the existing resume/retry tools.
    $manifest = Join-Path $typeOutput 'input_questions.jsonl'
    $records = @(Import-Csv -LiteralPath $questions | ForEach-Object {
        $_ | Add-Member -NotePropertyName dataset_type -NotePropertyValue $group.Folder -PassThru | ConvertTo-Json -Compress -Depth 20
    })
    $manifestText = ($records -join "`n") + "`n"
    if (Test-Path -LiteralPath $manifest) {
        if ([System.IO.File]::ReadAllText($manifest) -ne $manifestText) {
            throw "Dataset changed since the saved manifest: $manifest. Preserve the old reports before starting a new run."
        }
    }
    else {
        [System.IO.File]::WriteAllText($manifest, $manifestText, [System.Text.UTF8Encoding]::new($false))
    }
    $report = Join-Path $typeOutput 'raw_pipeline_v9.csv'
    $env:RESULT_JSONL_FILE = Join-Path $typeOutput 'raw_pipeline_v9.jsonl'
    $env:DEBUG_JSONL_FILE = Join-Path $typeOutput 'raw_pipeline_v9_debug.jsonl'
    $Host.UI.RawUI.WindowTitle = "Improvement8 - $Type - $($group.Folder)"
    Start-Transcript -Path (Join-Path $typeOutput 'terminal.log') -Append | Out-Null
    try {
        Write-Host "Running all questions in $questions"
        Write-Host "Saving results to $report"
        & $pythonExe -B $runner --env-file $envFile --questions $manifest --output $report --limit 0 --agent-consultation on
        $pipelineExit = $LASTEXITCODE
        Write-Host "Pipeline exit code: $pipelineExit"
        if ($pipelineExit -ne 0) { throw "Pipeline failed for $Type (exit $pipelineExit). See the runtime log printed above." }
    }
    finally {
        Stop-Transcript | Out-Null
    }
    return
}

# Validate all datasets before spending model calls or opening terminals.
$seenIds = [System.Collections.Generic.HashSet[string]]::new()
$total = 0
foreach ($group in $groups) {
    $questions = Join-Path $experimentRoot "dataset/$($group.Code).csv"
    $rows = @(Import-Csv -LiteralPath $questions)
    if ($rows.Count -eq 0) { throw "Empty dataset: $questions" }
    foreach ($column in @('global_question_id', 'question', 'ground_truth_answer')) {
        if ($rows[0].PSObject.Properties.Name -notcontains $column) { throw "Missing $column in $questions" }
    }
    foreach ($row in $rows) {
        if ([string]::IsNullOrWhiteSpace($row.question) -or [string]::IsNullOrWhiteSpace($row.global_question_id)) {
            throw "Missing question or ID in $questions"
        }
        if (-not $seenIds.Add($row.global_question_id)) { throw "Duplicate question ID: $($row.global_question_id)" }
    }
    $total += $rows.Count
    Write-Host "$($group.Code): $($rows.Count) questions -> $($group.Folder)"
}
Write-Host "Total: $total questions in eight independent terminals."
if ($ValidateOnly) { return }

# Compile once before concurrency; normal runs validate/reuse this same cache.
& $pythonExe -B $runner --env-file $envFile --prepare-knowledge
if ($LASTEXITCODE -ne 0) { throw 'Knowledge preparation failed; no terminals were launched.' }

$launches = @()
foreach ($group in $groups) {
    $arguments = @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass', '-File',
                   ('"' + $PSCommandPath + '"'), '-Type', $group.Code,
                   '-Python', ('"' + $pythonExe + '"'),
                   '-OutputRoot', ('"' + $runOutputRoot + '"'))
    # Visible consoles are intentional: the user requested eight terminals.
    $process = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $arguments `
                            -WorkingDirectory $experimentRoot -WindowStyle Normal -PassThru
    $launches += [PSCustomObject]@{ type = $group.Code; terminal_pid = $process.Id;
        output = (Join-Path $runOutputRoot $group.Folder); started_at = (Get-Date -Format o) }
}
New-Item -ItemType Directory -Path $runOutputRoot -Force | Out-Null
$launches | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runOutputRoot 'terminal_launches.json') -Encoding UTF8
$launches | Format-Table -AutoSize

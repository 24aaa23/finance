param(
    [string]$Java = 'java',
    [string]$FusekiJar = (Join-Path $PSScriptRoot 'tools/apache-jena-fuseki-6.1.0/fuseki-server.jar'),
    [string]$KgData = (Join-Path $PSScriptRoot 'kg_output_fixed/wealth_management_diverse_kg.ttl'),
    [ValidateRange(1, 65535)]
    [int]$Port = 3041,
    [ValidateRange(1, 600)]
    [int]$StartupTimeoutSeconds = 120,
    [switch]$ShowLogs
)
$ErrorActionPreference = 'Stop'
$javaExe = (Get-Command $Java -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$jarPath = (Resolve-Path -LiteralPath $FusekiJar).Path
$dataPath = (Resolve-Path -LiteralPath $KgData).Path
$runtime = Join-Path $PSScriptRoot '.runtime/fuseki'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$endpoint = "http://127.0.0.1:$Port/improvemnt11kgfixed/query"

function Wait-KgReady([System.Diagnostics.Process]$ServerProcess) {
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds) {
        if ($ServerProcess.HasExited) {
            throw "Fuseki exited before becoming ready. Check $runtime/stdout.log and stderr.log."
        }
        try {
            $response = Invoke-RestMethod -Uri $endpoint -Method Post `
                -ContentType 'application/x-www-form-urlencoded' `
                -Headers @{ Accept = 'application/sparql-results+json' } `
                -Body @{ query = 'ASK { ?s ?p ?o }' } -TimeoutSec 2
            if ($response.boolean -eq $true) { return }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "Fuseki did not become ready within $StartupTimeoutSeconds seconds. Check $runtime/stdout.log and stderr.log."
}

function Show-KgLogs([System.Diagnostics.Process]$ServerProcess) {
    $pidFile = Join-Path $runtime 'server.pid'
    $savedPid = 0
    if (-not (Test-Path -LiteralPath $pidFile) -or
        -not [int]::TryParse(([System.IO.File]::ReadAllText($pidFile)).Trim(), [ref]$savedPid) -or
        $savedPid -ne $ServerProcess.Id) {
        Write-Host 'This server was started in another terminal; its logs are in that terminal.'
        return
    }
    Write-Host 'Showing live Fuseki logs. Run your pipeline in other terminals.'
    Write-Host 'Ctrl+C closes this log view; the KG server keeps running.'
    $readers = @()
    try {
        foreach ($name in @('stdout.log', 'stderr.log')) {
            $path = Join-Path $runtime $name
            if (-not (Test-Path -LiteralPath $path)) { continue }
            $stream = [System.IO.File]::Open($path, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
            $stream.Seek(0, [System.IO.SeekOrigin]::End) | Out-Null
            $readers += [System.IO.StreamReader]::new($stream)
            Get-Content -LiteralPath $path -Tail 8
        }
        while (-not $ServerProcess.HasExited) {
            foreach ($reader in $readers) {
                while (-not $reader.EndOfStream) {
                    Write-Host $reader.ReadLine()
                }
            }
            Start-Sleep -Milliseconds 500
        }
        Write-Host 'The Fuseki server has stopped.'
    }
    finally {
        foreach ($reader in $readers) { $reader.Dispose() }
    }
}

# netstat reports listener ownership without requiring CIM networking access.
$listenerPids = @(& netstat.exe -ano -p tcp | ForEach-Object {
    if ($_ -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
        [int]$Matches[1]
    }
} | Sort-Object -Unique)
if ($listenerPids.Count -gt 0) {
    if ($listenerPids.Count -ne 1) {
        throw "Port $Port has multiple listeners. Refusing to launch or stop a server."
    }
    $existingPid = $listenerPids[0]
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$existingPid" -ErrorAction Stop
    $commandLine = $existing.CommandLine
    $fileMatch = [regex]::Match($commandLine, '--file(?:=|\s+)(?:"(?<quoted>[^"]+)"|(?<bare>\S+))')
    $loadedFile = if ($fileMatch.Groups['quoted'].Success) {
        $fileMatch.Groups['quoted'].Value
    } else { $fileMatch.Groups['bare'].Value }
    $sameFile = [System.IO.Path]::IsPathRooted($loadedFile) -and
        [string]::Equals([System.IO.Path]::GetFullPath($loadedFile), $dataPath,
                        [System.StringComparison]::OrdinalIgnoreCase)
    $isExpectedServer = $existing.Name -eq 'java.exe' -and $sameFile -and
        $commandLine -match 'fuseki-server\.jar"?(?:\s|$)' -and
        $commandLine -match "(?:^|\s)--port(?:=|\s+)$Port(?:\s|$)" -and
        $commandLine -match '(?:^|\s)/improvemnt11kgfixed(?:\s|$)' -and
        $commandLine -match '(?:^|\s)--localhost(?:\s|$)' -and
        $commandLine -notmatch '(?:^|\s)--update(?:\s|$)'
    if (-not $isExpectedServer) {
        throw "Port $Port is owned by PID $existingPid; its command does not match the read-only improvemnt11kgfixed KG. No process was stopped."
    }
    $existingProcess = Get-Process -Id $existingPid -ErrorAction Stop
    Wait-KgReady $existingProcess
    Write-Host "Reusing verified improvemnt11kgfixed KG server (PID $existingPid)."
    Write-Host "Endpoint ready: $endpoint"
    if ($ShowLogs) { Show-KgLogs $existingProcess }
    return
}
$arguments = @('-Xmx2g', '-jar', ('"' + $jarPath + '"'), '--localhost', "--port=$Port",
               ('--file="' + $dataPath + '"'), '/improvemnt11kgfixed')
$process = Start-Process -FilePath $javaExe -ArgumentList $arguments -WorkingDirectory $runtime `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'stdout.log') `
    -RedirectStandardError (Join-Path $runtime 'stderr.log')
$process.Id | Set-Content -LiteralPath (Join-Path $runtime 'server.pid')
Write-Host "Started read-only improvemnt11kgfixed KG server (PID $($process.Id)); waiting for the dataset."
Wait-KgReady $process
Write-Host "Endpoint ready: $endpoint"
Write-Host "Startup logs: $runtime"
if ($ShowLogs) { Show-KgLogs $process }

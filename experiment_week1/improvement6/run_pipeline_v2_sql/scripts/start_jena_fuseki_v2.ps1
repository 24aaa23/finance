param(
    [string]$FusekiHome = 'C:\Users\AMAN KUMAR SINGH\Desktop\financial\code_final\tools\apache-jena-fuseki-6.1.0',
    [string]$DatasetName = 'wealth',
    [int]$Port = 3030,
    [string]$HostAddress = '127.0.0.1',
    [string]$InstanceFile = '',
    [switch]$Background
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pipelineDir = Split-Path -Parent $scriptDir
$experimentDir = Split-Path -Parent $pipelineDir

if (-not $InstanceFile) {
    $InstanceFile = Join-Path $experimentDir 'kg_output_fixed\wealth_management_diverse_kg.ttl'
}

$fusekiBat = Join-Path $FusekiHome 'fuseki-server.bat'
if (-not (Test-Path -LiteralPath $fusekiBat -PathType Leaf)) {
    throw "Missing Fuseki server: $fusekiBat"
}
if (-not (Test-Path -LiteralPath $InstanceFile -PathType Leaf)) {
    throw "Missing RDF instance file: $InstanceFile"
}

$endpoint = "http://$HostAddress`:$Port/$DatasetName/query"
Write-Output "Starting Fuseki"
Write-Output "Fuseki:   $fusekiBat"
Write-Output "Data:     $InstanceFile"
Write-Output "Endpoint: $endpoint"
Write-Output ""
Write-Output "Pipeline default FUSEKI_ENDPOINT should be: $endpoint"

$arguments = @(
    '--localhost',
    "--port=$Port",
    "--file=$InstanceFile",
    "/$DatasetName"
)

if ($Background) {
    # Run Java directly so Windows never follows a .bat file association.
    $java = (Get-Command java -ErrorAction Stop).Source
    $javaArguments = @(
        '-Xmx4G',
        '-cp', 'fuseki-server.jar',
        'org.apache.jena.fuseki.main.cmds.FusekiServerUICmd',
        '--localhost',
        "--port=$Port",
        ('--file="{0}"' -f $InstanceFile),
        "/$DatasetName"
    )
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $stdoutLog = Join-Path $FusekiHome ("fuseki_{0}.stdout.log" -f $timestamp)
    $stderrLog = Join-Path $FusekiHome ("fuseki_{0}.stderr.log" -f $timestamp)
    Start-Process -FilePath $java -ArgumentList $javaArguments -WorkingDirectory $FusekiHome -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Write-Output "Fuseki launch requested in background. Wait a few seconds before running the pipeline."
    Write-Output "Fuseki stdout: $stdoutLog"
    Write-Output "Fuseki stderr: $stderrLog"
} else {
    & $fusekiBat @arguments
}


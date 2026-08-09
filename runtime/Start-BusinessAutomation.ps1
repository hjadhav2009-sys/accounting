[CmdletBinding()]
param([switch]$NoBrowser,[switch]$StartLocalAI)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$stateDirectory = Join-Path $projectRoot '.runtime'
$stateFile = Join-Path $stateDirectory 'processes.json'
$logDirectory = Join-Path $stateDirectory 'logs'
New-Item -ItemType Directory -Force -Path $stateDirectory,$logDirectory | Out-Null

function Read-DotEnv([string]$path) {
    $values = @{}
    if (Test-Path -LiteralPath $path) {
        foreach ($line in Get-Content -LiteralPath $path) {
            if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $values[$matches[1]] = $matches[2].Trim() }
        }
    }
    return $values
}
function Port-InUse([int]$port) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$port)
    try {
        $probe.Server.ExclusiveAddressUse = $true
        $probe.Start()
        return $false
    } catch [System.Net.Sockets.SocketException] {
        return $true
    } finally {
        try { $probe.Stop() } catch { }
    }
}
function Require-FreePort([string]$name,[int]$port) {
    if (Port-InUse $port) { throw "$name cannot start: localhost port $port is already in use. Stop the owning application explicitly; no process was killed." }
}
function Start-Owned([string]$name,[string]$file,[string[]]$arguments,[string]$workingDirectory) {
    $stdout = Join-Path $logDirectory "$name.out.log"; $stderr = Join-Path $logDirectory "$name.err.log"
    $process = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $workingDirectory -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Start-Sleep -Milliseconds 700
    if ($process.HasExited) { throw "$name exited during startup. See $stderr" }
    return [ordered]@{ pid=$process.Id; executable=[System.IO.Path]::GetFullPath($file); project_root=$projectRoot; started_at=(Get-Date).ToString('o') }
}

$configuration = Read-DotEnv (Join-Path $projectRoot '.env')
foreach ($entry in $configuration.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable([string]$entry.Key,[string]$entry.Value,'Process')
}
$frontendPort = if ($configuration.FRONTEND_PORT) { [int]$configuration.FRONTEND_PORT } else { 3000 }
$backendPort = if ($configuration.BACKEND_PORT) { [int]$configuration.BACKEND_PORT } else { 8000 }
$postgresPort = if ($configuration.POSTGRES_PORT) { [int]$configuration.POSTGRES_PORT } else { 5432 }
$localAiPort = if ($configuration.LOCAL_AI_PORT) { [int]$configuration.LOCAL_AI_PORT } else { 8080 }
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontend = Join-Path $projectRoot 'v2\frontend'
if (-not (Test-Path -LiteralPath $python)) { throw "Python virtual environment is missing: $python" }
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules'))) { throw 'Frontend dependencies are missing. Run npm install in v2\frontend.' }
if (-not (Port-InUse $postgresPort)) { throw "PostgreSQL is not listening on localhost:$postgresPort. Start the installed PostgreSQL service first." }
Require-FreePort 'FastAPI' $backendPort; Require-FreePort 'Next.js' $frontendPort

$owned = [ordered]@{}
try {
    if ($StartLocalAI) {
        Require-FreePort 'llama.cpp' $localAiPort
        $llamaExe = $configuration.LLAMA_SERVER_EXE; $modelPath = $configuration.LOCAL_AI_MODEL_PATH
        if (-not $llamaExe -or -not $modelPath) { throw 'Set LLAMA_SERVER_EXE and LOCAL_AI_MODEL_PATH before using -StartLocalAI.' }
        $llamaExe = [System.IO.Path]::GetFullPath($llamaExe); $modelPath = [System.IO.Path]::GetFullPath($modelPath)
        if (-not (Test-Path -LiteralPath $llamaExe) -or -not (Test-Path -LiteralPath $modelPath)) { throw 'Configured llama.cpp executable or model path does not exist.' }
        $owned.local_ai = Start-Owned 'local-ai' $llamaExe @('-m',$modelPath,'--host','127.0.0.1','--port',"$localAiPort") $projectRoot
    }
    $owned.backend = Start-Owned 'backend' $python @('-m','uvicorn','v2.backend.app.main:app','--host','127.0.0.1','--port',"$backendPort") $projectRoot
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $nextCli = Join-Path $frontend 'node_modules\next\dist\bin\next'
    $frontendMode = if (Test-Path -LiteralPath (Join-Path $frontend '.next\BUILD_ID')) { 'start' } else { 'dev' }
    $owned.frontend = Start-Owned 'frontend' $node @($nextCli,$frontendMode,'-p',"$frontendPort",'-H','127.0.0.1') $frontend
    $owned | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding utf8
    Write-Host "Business Automation V2 started on http://127.0.0.1:$frontendPort"
    Write-Host "Process ownership file: $stateFile"
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$frontendPort/login" }
} catch {
    foreach ($entry in $owned.GetEnumerator()) { Stop-Process -Id $entry.Value.pid -ErrorAction SilentlyContinue }
    throw
}

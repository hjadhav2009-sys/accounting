[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$stateFile = Join-Path $projectRoot '.runtime\processes.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Host 'No application-owned process record exists. Nothing was stopped.'; exit 0 }
$state = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
$stopped = 0
function Stop-OwnedTree([int]$processId) {
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $processId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) { Stop-OwnedTree ([int]$child.ProcessId) }
    if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $processId
        Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
        $script:stopped++
    }
}
foreach ($property in $state.PSObject.Properties) {
    $record = $property.Value; $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.pid)" -ErrorAction SilentlyContinue
    $command = if ($cim) { [string]$cim.CommandLine } else { '' }
    $actualExecutable = if ($cim) { [string]$cim.ExecutablePath } else { '' }
    $expectedExecutable = [System.IO.Path]::GetFullPath([string]$record.executable)
    $ownedCommand = $command.IndexOf($projectRoot,[System.StringComparison]::OrdinalIgnoreCase) -ge 0
    $ownedExecutable = $actualExecutable -and ([System.IO.Path]::GetFullPath($actualExecutable) -eq $expectedExecutable)
    if (-not ($ownedCommand -or $ownedExecutable)) {
        Write-Warning "Refused to stop PID $($record.pid): its command line is not owned by this project."
        continue
    }
    Stop-OwnedTree ([int]$record.pid)
    Write-Host "Stopped $($property.Name) process tree (root PID $($record.pid))."
}
Remove-Item -LiteralPath $stateFile -Force
Write-Host "Stopped $stopped application-owned process(es). PostgreSQL was not stopped."

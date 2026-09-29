<#
.SYNOPSIS
    Phase 0-B preflight for the VPN-reachable GPU LLM endpoint (Windows native).

.DESCRIPTION
    Runs the checks from the ECLSS Recursive Subsystem Engineering Agents design
    (section 29): Python version, host reachability, TCP endpoint, LLM health API,
    structured JSON generation, and a small parallel-request smoke.

    The endpoint is never stored in the repository. Supply it through the
    environment or the parameters below, after connecting the VPN yourself —
    this script does not touch VPN credentials and does not dial the VPN.

        $env:EA_LLM_BASE_URL = "http://<private-host>:<port>"
        $env:EA_LLM_MODEL    = "<served model id>"   # optional
        $env:EA_LLM_API_KEY  = "<token>"             # optional

.EXAMPLE
    .\scripts\windows\preflight_remote_llm.ps1 -Host 10.0.0.5

.EXAMPLE
    $env:EA_LLM_BASE_URL = "http://10.0.0.5:8000/v1"
    .\scripts\windows\preflight_remote_llm.ps1
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = $env:EA_LLM_BASE_URL,
    [string]$TargetHost,
    [string]$Ports = "8000,8001,11434",
    [string]$Model = $env:EA_LLM_MODEL,
    [int]$Concurrency = 4,
    [double]$TimeoutSeconds = 30,
    [string]$Python,
    [string]$ReportPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$preflight = Join-Path $repoRoot "src\scripts\preflight_remote_llm.py"
if (-not (Test-Path $preflight)) {
    throw "preflight module not found: $preflight"
}

if (-not $Python) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { $Python = $venvPython } else { $Python = "python" }
}

Write-Host "== ECLSS remote LLM preflight ==" -ForegroundColor Cyan
Write-Host "repo    : $repoRoot"
Write-Host "python  : $Python"
if ($BaseUrl) { Write-Host "base url: $BaseUrl" }
if ($TargetHost) { Write-Host "host    : $TargetHost" }

# Report VPN profile state without reading any credential material.
try {
    $vpn = Get-VpnConnection -ErrorAction SilentlyContinue |
        Select-Object Name, ConnectionStatus
    if ($vpn) {
        Write-Host "`n-- VPN profiles --" -ForegroundColor Cyan
        $vpn | Format-Table -AutoSize | Out-String | Write-Host
    }
} catch {
    Write-Host "VPN profile query unavailable (non-fatal)."
}

$pyArgs = @($preflight, "--ports", $Ports, "--concurrency", $Concurrency,
            "--timeout-s", $TimeoutSeconds)
if ($BaseUrl)    { $pyArgs += @("--base-url", $BaseUrl) }
if ($TargetHost) { $pyArgs += @("--host", $TargetHost) }
if ($Model)      { $pyArgs += @("--model", $Model) }
if ($ReportPath) { $pyArgs += @("--report", $ReportPath) }

# src/ must be importable so the probe can reuse core.llm.parsing.
$env:PYTHONPATH = (Join-Path $repoRoot "src")

& $Python @pyArgs
$exit = $LASTEXITCODE

if ($exit -eq 0) {
    Write-Host "`nGate 0 (remote LLM): GO" -ForegroundColor Green
} else {
    Write-Host "`nGate 0 (remote LLM): NO-GO — see the report above." -ForegroundColor Yellow
}
exit $exit

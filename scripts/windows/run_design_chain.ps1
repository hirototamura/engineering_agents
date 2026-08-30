# Run one design->verify chain, the way the three archived chains were run.
#
# Each round simulates the habitat, hands the run to the design agent, and
# installs whatever the agent proposes as the next round's hardware. The chain's
# single answer lands in <output>\chain_final_answer.json.
#
#   .\scripts\windows\run_design_chain.ps1
#   .\scripts\windows\run_design_chain.ps1 -Rounds 5
#   .\scripts\windows\run_design_chain.ps1 -Provider ollama -Model qwen3:8b
#
# The design side needs an LLM. `ea doctor` says whether one is reachable.
# What the archived chains under experiments\runs\ were run with, and how to
# reproduce each: experiments\README.md.

[CmdletBinding()]
param(
    [ValidateRange(1, 50)][int]$Rounds = 0,
    [ValidateSet('ollama', 'vllm')][string]$Provider = '',
    [string]$Model = '',
    [string]$RunId = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Extra
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$ea = Get-Command ea -ErrorAction SilentlyContinue
if ($null -ne $ea) {
    $exe = 'ea'
    $argv = @('run', 'ssos_eclss_loop')
} else {
    # Editable install not on PATH; the package is importable from src\.
    $env:PYTHONPATH = "$repoRoot\src"
    $exe = 'python'
    $argv = @('-m', 'tools.cli', 'run', 'ssos_eclss_loop')
}

if ($Rounds -gt 0)   { $argv += @('--iterate', "$Rounds") }
if ($Provider -ne '') { $argv += @('--llm-provider', $Provider) }
if ($Model -ne '')    { $argv += @('--llm-model', $Model) }
if ($RunId -ne '')    { $argv += @('--run-id', $RunId) }
if ($Extra)           { $argv += $Extra }

Write-Host "==> $exe $($argv -join ' ')"
& $exe @argv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Chain finished. What to read, in order:'
Write-Host '  chain_final_answer.json        the one design the whole chain answers with'
Write-Host '  chain_summary.json             survivors first vs last, and the paired replay'
Write-Host '  compact_chain_memory.json      the note each round left for the next'
Write-Host '  NN\design_decision_state.json  the page the model saw that round, and its answer'
Write-Host ''
Write-Host 'To turn a chain into the per-round table the docs cite:'
Write-Host '  cd experiments; python analysis\analyze_ssos_iter.py --root <chain dir> --prefix mychain'

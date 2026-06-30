# Create a persistent SSOS container for host `ea run ssos_eclss_loop` (Windows).
# Requires Docker Desktop. Run from PowerShell in the engineering_agents repo root.
$ErrorActionPreference = "Stop"

$Image = if ($env:SSOS_IMAGE) { $env:SSOS_IMAGE } else { "ghcr.io/space-station-os/space_station_os:latest" }
$Platform = if ($env:SSOS_PLATFORM) { $env:SSOS_PLATFORM } else { "linux/amd64" }
$ContainerName = if ($env:SSOS_CONTAINER_NAME) { $env:SSOS_CONTAINER_NAME } else { "ssos" }

$ScriptsDir = Split-Path -Parent $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptsDir "..\..")

$Volumes = @(
  "-v", "${ScriptsDir}/ssos-container-setup.sh:/root/ssos-container-setup.sh:ro",
  "-v", "${ScriptsDir}/ssos-eclss-headless.sh:/root/ssos-eclss-headless.sh:ro",
  "-v", "${ScriptsDir}/ssos-headless.launch.py:/root/ssos-headless.launch.py:ro",
  "-v", "${ScriptsDir}/ssos-eps.launch.py:/root/ssos-eps.launch.py:ro",
  "-v", "${RepoRoot}/src:/ea/src",
  "-v", "${RepoRoot}/src/experiments/results:/ea/results"
)

Write-Host "==> SSOS detached container (for ea run)"
Write-Host "    Repo:      $RepoRoot"
Write-Host "    Container: $ContainerName"
Write-Host ""

docker info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Docker daemon is not running. Start Docker Desktop and retry."
}

Write-Host "==> Pulling prebuilt image (platform: $Platform)..."
docker pull --platform $Platform $Image

docker stop $ContainerName 2>$null
docker rm $ContainerName 2>$null

Write-Host "==> Creating detached container..."
$runArgs = @(
  "run", "-d", "--init",
  "--name", $ContainerName,
  "--platform", $Platform
) + $Volumes + @(
  "-e", "SSOS_CONTAINER_DETACHED=1",
  $Image,
  "bash", "-lc", "bash /root/ssos-container-setup.sh; exec sleep infinity"
)
& docker @runArgs

Write-Host ""
Write-Host "==> Verifying mounts..."
docker exec $ContainerName test -d /ea/src/scenario/ssos_eclss_loop
docker exec $ContainerName test -f /root/ssos-eclss-headless.sh
Write-Host "    src mount OK"
Write-Host "    headless helpers OK"
Write-Host ""
Write-Host "Next (on the host):"
Write-Host "  cd `"$RepoRoot`""
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50"
Write-Host ""
Write-Host "If stopped later: docker start $ContainerName"

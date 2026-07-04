# Interactive SSOS container shell (Windows). For ea run use ssos-run-detached.ps1.
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

docker info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Docker daemon is not running. Start Docker Desktop and retry."
}

docker pull --platform $Platform $Image
docker rm -f $ContainerName 2>$null

$runArgs = @(
  "run", "-it", "--rm", "--init",
  "--name", $ContainerName,
  "--platform", $Platform
) + $Volumes + @(
  $Image,
  "bash", "/root/ssos-container-setup.sh"
)
& docker @runArgs

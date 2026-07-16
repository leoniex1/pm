$ErrorActionPreference = "Stop"

$container = "pm-mvp"

Write-Host "Stopping and removing container: $container"
docker rm -f $container | Out-Host

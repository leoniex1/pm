$ErrorActionPreference = "Stop"

$image = "pm-mvp"
$container = "pm-mvp"

Write-Host "Building Docker image: $image"
docker build -t $image .

Write-Host "Stopping existing container if present: $container"
$existingContainer = docker ps -a --filter "name=^$container$" --format "{{.Names}}"
if ($existingContainer -eq $container) {
	docker rm -f $container | Out-Null
}

Write-Host "Starting container: $container"
docker run -d --name $container -p 8000:8000 $image | Out-Host

Write-Host "App should be available at http://localhost:8000"

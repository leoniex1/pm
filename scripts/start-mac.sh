#!/usr/bin/env sh
set -eu

IMAGE="pm-mvp"
CONTAINER="pm-mvp"

echo "Building Docker image: ${IMAGE}"
docker build -t "${IMAGE}" .

echo "Stopping existing container if present: ${CONTAINER}"
docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true

echo "Starting container: ${CONTAINER}"
docker run -d --name "${CONTAINER}" -p 8000:8000 "${IMAGE}"

echo "App should be available at http://localhost:8000"

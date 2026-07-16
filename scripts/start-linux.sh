#!/usr/bin/env sh
set -eu

IMAGE="pm-mvp"
CONTAINER="pm-mvp"
DATA_DIR="$(pwd)/backend/data"
ENV_FILE="$(pwd)/.env"

mkdir -p "${DATA_DIR}"

echo "Building Docker image: ${IMAGE}"
docker build -t "${IMAGE}" .

echo "Stopping existing container if present: ${CONTAINER}"
docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true

echo "Starting container: ${CONTAINER}"
if [ -f "${ENV_FILE}" ]; then
docker run -d --name "${CONTAINER}" -p 8000:8000 -v "${DATA_DIR}:/app/backend/data" --env-file "${ENV_FILE}" "${IMAGE}"
else
echo "Warning: .env file not found at project root; running without --env-file"
docker run -d --name "${CONTAINER}" -p 8000:8000 -v "${DATA_DIR}:/app/backend/data" "${IMAGE}"
fi

echo "App should be available at http://localhost:8000"

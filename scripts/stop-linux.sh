#!/usr/bin/env sh
set -eu

CONTAINER="pm-mvp"

echo "Stopping and removing container: ${CONTAINER}"
docker rm -f "${CONTAINER}"

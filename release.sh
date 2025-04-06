#!/bin/sh
set -e # Exit immediately if a command exits with a non-zero status.

SCRIPT_VERSION="17.0.4"

IMAGE_NAME="masterkain/postgresql-backup-s3"
IMAGE_TAG="${SCRIPT_VERSION}"
LATEST_TAG="latest"

# Define target platforms
PLATFORMS="linux/amd64,linux/arm64,linux/arm/v7"

echo "--- Setting up buildx ---"
docker buildx create --use --name multiarch-builder || true
docker buildx inspect --bootstrap

echo "--- Building and pushing multi-arch image ${IMAGE_NAME}:${IMAGE_TAG} and ${IMAGE_NAME}:${LATEST_TAG} for platforms: ${PLATFORMS} ---"

docker buildx build \
  --platform "${PLATFORMS}" \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  --tag "${IMAGE_NAME}:${LATEST_TAG}" \
  --push \
  .

BUILD_STATUS=$?
if [ ${BUILD_STATUS} -ne 0 ]; then
  echo "!!! Docker buildx build failed with status: ${BUILD_STATUS} !!!"
  exit ${BUILD_STATUS}
fi

echo "--- Multi-arch build and push completed successfully ---"

echo "--- Cleaning up buildx builder ---"
docker buildx rm multiarch-builder

exit 0

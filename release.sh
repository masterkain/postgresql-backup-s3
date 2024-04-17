#!/bin/sh

docker buildx create --use
docker buildx ls
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7,linux/arm/v6 \
  --tag masterkain/postgresql-backup-s3:16.0.5 \
  --push \
  .

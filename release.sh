#!/bin/sh

docker buildx create --use
docker buildx ls
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v8,linux/arm/v7,linux/arm/v6 \
  --tag masterkain/postgresql-backup-s3:17.0.1 \
  --push \
  .

#!/bin/bash

# 设置变量
IMAGE_NAME="palfans/m3u-helper"
VERSION=$(git describe --tags --always)
PLATFORMS="linux/amd64,linux/arm64,linux/arm/v7"

# 确保已启用buildx
docker buildx create --use

# 构建并推送多架构镜像
docker buildx build \
  --platform ${PLATFORMS} \
  --tag ${IMAGE_NAME}:latest \
  --tag ${IMAGE_NAME}:${VERSION} \
  --push \
  . 
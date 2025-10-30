#!/usr/bin/env bash
#
# 推送镜像到云服务平台（Harbor）
# 用途：将 GHCR 镜像同步到 <registry>/<project>/<image>
#

set -euo pipefail

# 参数与环境变量（参数优先，其次 env，最后默认）
TAG="${1:-${TAG:-latest}}"
HARBOR_REGISTRY="${2:-${HARBOR_REGISTRY:-harbor1.suanleme.cn}}"
HARBOR_PROJECT="${3:-${HARBOR_PROJECT:-}}"
HARBOR_USERNAME="${4:-${HARBOR_USERNAME:-}}"
GHCR_IMAGE="${5:-${GHCR_IMAGE:-ghcr.io/feather-2/pbx-ocr-deploy}}"
HARBOR_IMAGE_NAME="${6:-${HARBOR_IMAGE_NAME:-pbx-ocr-deploy}}"
HARBOR_IMAGE="$HARBOR_REGISTRY/$HARBOR_PROJECT/$HARBOR_IMAGE_NAME"

if [[ -z "$HARBOR_PROJECT" || -z "$HARBOR_USERNAME" ]]; then
  echo "[ERROR] HARBOR_PROJECT/HARBOR_USERNAME 未设置。" >&2
  echo "用法: ./push-to-suanleme.sh [TAG] [REGISTRY] [PROJECT] [USERNAME] [GHCR_IMAGE] [HARBOR_IMAGE_NAME]" >&2
  exit 1
fi

echo "=================================================="
echo "推送镜像到云服务平台，如共绩算力私有仓库"
echo "=================================================="
echo "TAG:         $TAG"
echo "REGISTRY:    $HARBOR_REGISTRY"
echo "PROJECT:     $HARBOR_PROJECT"
echo "USERNAME:    $HARBOR_USERNAME"
echo "GHCR_IMAGE:  $GHCR_IMAGE"
echo "HARBOR_IMAGE:$HARBOR_IMAGE:$TAG"
echo "=================================================="

# 1. 登录到云服务平台，如共绩算力镜像仓库
echo ""
echo "Step 1: 登录到云服务平台，如共绩算力镜像仓库..."
echo "请输入仓库密码（用户名: $HARBOR_USERNAME）"
docker login "$HARBOR_REGISTRY" --username="$HARBOR_USERNAME"

# 2. 拉取 GHCR 镜像
echo ""
echo "Step 2: 从 GitHub Container Registry 拉取镜像..."
docker pull "$GHCR_IMAGE:$TAG"

# 3. 重新打标签
echo ""
echo "Step 3: 重新打标签为云服务平台，如共绩算力镜像名..."
docker tag "$GHCR_IMAGE:$TAG" "$HARBOR_IMAGE:$TAG"

# 4. 推送到云服务平台，如共绩算力
echo ""
echo "Step 4: 推送到云服务平台，如共绩算力私有仓库（5.84 GB，需要一些时间）..."
docker push "$HARBOR_IMAGE:$TAG"

# 5. 清理本地标签（可选）
echo ""
echo "Step 5: 清理本地临时标签..."
docker rmi "$HARBOR_IMAGE:$TAG" || true

echo ""
echo "=================================================="
echo "✅ 推送成功!"
echo "=================================================="
echo "镜像地址: $HARBOR_IMAGE:$TAG"
echo ""
echo "在云服务平台，如共绩算力上使用此镜像："
echo "  docker pull $HARBOR_IMAGE:$TAG"
echo ""
echo "或在 docker-compose.yml 中使用："
echo "  image: $HARBOR_IMAGE:$TAG"
echo "=================================================="

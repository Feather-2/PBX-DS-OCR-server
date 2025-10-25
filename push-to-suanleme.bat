@echo off
REM 推送镜像到云服务平台，如共绩算力私有仓库
REM 用途：将 GHCR 镜像同步到 harbor1.suanleme.cn/wing

setlocal

REM 配置
set GHCR_IMAGE=ghcr.io/feather-2/pbx-ocr-deploy
set HARBOR_REGISTRY=harbor1.suanleme.cn
set HARBOR_PROJECT=wing
set HARBOR_IMAGE=%HARBOR_REGISTRY%/%HARBOR_PROJECT%/pbx-ocr-deploy
set HARBOR_USERNAME=wing

REM 从参数获取标签，默认为 latest
set TAG=%1
if "%TAG%"=="" set TAG=latest

echo ==================================================
echo 推送镜像到云服务平台，如共绩算力私有仓库
echo ==================================================
echo 源镜像:   %GHCR_IMAGE%:%TAG%
echo 目标仓库: %HARBOR_IMAGE%:%TAG%
echo ==================================================

REM 1. 登录到云服务平台，如共绩算力镜像仓库
echo.
echo Step 1: 登录到云服务平台，如共绩算力镜像仓库...
echo 请输入仓库密码（用户名: %HARBOR_USERNAME%）
docker login %HARBOR_REGISTRY% --username=%HARBOR_USERNAME%
if errorlevel 1 goto :error

REM 2. 拉取 GHCR 镜像
echo.
echo Step 2: 从 GitHub Container Registry 拉取镜像...
docker pull %GHCR_IMAGE%:%TAG%
if errorlevel 1 goto :error

REM 3. 重新打标签
echo.
echo Step 3: 重新打标签为云服务平台，如共绩算力镜像名...
docker tag %GHCR_IMAGE%:%TAG% %HARBOR_IMAGE%:%TAG%
if errorlevel 1 goto :error

REM 4. 推送到云服务平台，如共绩算力
echo.
echo Step 4: 推送到云服务平台，如共绩算力私有仓库（5.84 GB，需要一些时间）...
docker push %HARBOR_IMAGE%:%TAG%
if errorlevel 1 goto :error

REM 5. 清理本地标签（可选）
echo.
echo Step 5: 清理本地临时标签...
docker rmi %HARBOR_IMAGE%:%TAG% 2>nul

echo.
echo ==================================================
echo ✅ 推送成功!
echo ==================================================
echo 镜像地址: %HARBOR_IMAGE%:%TAG%
echo.
echo 在云服务平台，如共绩算力上使用此镜像：
echo   docker pull %HARBOR_IMAGE%:%TAG%
echo.
echo 或在 docker-compose.yml 中使用：
echo   image: %HARBOR_IMAGE%:%TAG%
echo ==================================================
goto :end

:error
echo.
echo ❌ 推送失败，请检查错误信息
exit /b 1

:end
endlocal

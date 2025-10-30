@echo off
REM 推送镜像到云服务平台，如共绩算力私有仓库
REM 支持环境变量 + 命令行参数（参数优先于环境变量）
REM 用途：将 GHCR 镜像同步到 <registry>/<project>/<image>

setlocal ENABLEDELAYEDEXPANSION

REM ========================
REM 参数与环境变量优先级
REM 用法: push-to-suanleme.bat [TAG] [REGISTRY] [PROJECT] [USERNAME] [GHCR_IMAGE] [HARBOR_IMAGE_NAME]
REM 说明: 若未提供位置参数，则读取环境变量；仍未设置则使用默认值/报错
REM ========================

REM 1) TAG
if not "%1"=="" ( set TAG=%1 )
if "%TAG%"=="" set TAG=latest

REM 2) REGISTRY
if "%HARBOR_REGISTRY%"=="" set HARBOR_REGISTRY=harbor1.suanleme.cn
if not "%2"=="" set HARBOR_REGISTRY=%2

REM 3) PROJECT
if not "%3"=="" set HARBOR_PROJECT=%3
REM 若仍为空则尝试使用现有环境变量，否则报错
if "%HARBOR_PROJECT%"=="" (
  echo [ERROR] HARBOR_PROJECT 未设置。请设置环境变量 HARBOR_PROJECT 或作为第3个参数传入。
  echo 用法: %~n0 [TAG] [REGISTRY] [PROJECT] [USERNAME] [GHCR_IMAGE] [HARBOR_IMAGE_NAME]
  exit /b 1
)

REM 4) USERNAME
if not "%4"=="" set HARBOR_USERNAME=%4
if "%HARBOR_USERNAME%"=="" (
  echo [ERROR] HARBOR_USERNAME 未设置。请设置环境变量 HARBOR_USERNAME 或作为第4个参数传入。
  exit /b 1
)

REM 5) GHCR 源镜像（可通过 env GHCR_IMAGE 覆盖）
if "%GHCR_IMAGE%"=="" set GHCR_IMAGE=ghcr.io/feather-2/pbx-ocr-deploy
if not "%5"=="" set GHCR_IMAGE=%5

REM 6) Harbor 目标镜像名（repo 内部名，不含 registry/project）
if "%HARBOR_IMAGE_NAME%"=="" set HARBOR_IMAGE_NAME=pbx-ocr-deploy
if not "%6"=="" set HARBOR_IMAGE_NAME=%6

set HARBOR_IMAGE=%HARBOR_REGISTRY%/%HARBOR_PROJECT%/%HARBOR_IMAGE_NAME%

echo ==================================================
echo 推送镜像到云服务平台（Harbor）
echo ==================================================
echo TAG:         %TAG%
echo REGISTRY:    %HARBOR_REGISTRY%
echo PROJECT:     %HARBOR_PROJECT%
echo USERNAME:    %HARBOR_USERNAME%
echo GHCR_IMAGE:  %GHCR_IMAGE%
echo HARBOR_IMAGE:%HARBOR_IMAGE%
echo ==================================================

REM 1. 登录到 Harbor
echo.
echo Step 1: 登录 Harbor（%HARBOR_REGISTRY%）...
docker login %HARBOR_REGISTRY% --username=%HARBOR_USERNAME%
if errorlevel 1 goto :error

REM 2. 拉取 GHCR 源镜像
echo.
echo Step 2: 拉取 GHCR 镜像 %GHCR_IMAGE%:%TAG% ...
docker pull %GHCR_IMAGE%:%TAG%
if errorlevel 1 goto :error

REM 3. 重新打标签为 Harbor 目标镜像
echo.
echo Step 3: 重打标签 -> %HARBOR_IMAGE%:%TAG%
docker tag %GHCR_IMAGE%:%TAG% %HARBOR_IMAGE%:%TAG%
if errorlevel 1 goto :error

REM 4. 推送到 Harbor
echo.
echo Step 4: 推送到 Harbor（可能耗时较长）...
docker push %HARBOR_IMAGE%:%TAG%
if errorlevel 1 goto :error

REM 5. 清理本地标签（可选）
echo.
echo Step 5: 清理临时标签...
docker rmi %HARBOR_IMAGE%:%TAG% 2>nul

echo.
echo ==================================================
echo ✅ 推送成功!
echo ==================================================
echo 镜像地址: %HARBOR_IMAGE%:%TAG%
echo ==================================================
goto :end

:error
echo.
echo ❌ 推送失败，请检查错误信息
exit /b 1

:end
endlocal

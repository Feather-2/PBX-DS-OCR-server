# Docker Desktop 数据迁移脚本 - 简化版
# 目标位置: G:\dockerfile

$TargetLocation = "G:\dockerfile\data"
$TempExport = "G:\temp_docker_export"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker Desktop 数据迁移到 G:\dockerfile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 检查当前 Docker 数据
Write-Host "`n[1/10] 检查当前数据..." -ForegroundColor Yellow
$currentPath = "C:\Users\wing\AppData\Local\Docker\wsl\disk"
if (Test-Path $currentPath) {
    $vhdxFiles = Get-ChildItem -Path $currentPath -Filter "*.vhdx" -Recurse -ErrorAction SilentlyContinue
    foreach ($file in $vhdxFiles) {
        $sizeGB = [math]::Round($file.Length/1GB, 2)
        Write-Host "   发现: $($file.Name) - $sizeGB GB" -ForegroundColor White
    }
}

# 检查 G 盘空间
Write-Host "`n[2/10] 检查 G 盘空间..." -ForegroundColor Yellow
$drive = Get-PSDrive -Name "G" -ErrorAction SilentlyContinue
if ($drive) {
    $freeSpaceGB = [math]::Round($drive.Free/1GB, 2)
    Write-Host "   G: 可用空间: $freeSpaceGB GB" -ForegroundColor White
} else {
    Write-Host "   错误: G 盘不存在！" -ForegroundColor Red
    exit 1
}

# 创建目录
Write-Host "`n[3/10] 创建目标目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $TargetLocation | Out-Null
New-Item -ItemType Directory -Force -Path $TempExport | Out-Null
Write-Host "   完成" -ForegroundColor Green

# 提示关闭 Docker
Write-Host "`n[4/10] 请先关闭 Docker Desktop..." -ForegroundColor Yellow
Write-Host "   1. 右键托盘的 Docker 图标" -ForegroundColor Cyan
Write-Host "   2. 点击 'Quit Docker Desktop'" -ForegroundColor Cyan
Write-Host "   3. 关闭后，按回车继续..." -ForegroundColor Cyan
Read-Host

# 关闭 WSL
Write-Host "`n[5/10] 关闭 WSL..." -ForegroundColor Yellow
wsl --shutdown
Start-Sleep -Seconds 3
Write-Host "   完成" -ForegroundColor Green

# 查看当前分发版
Write-Host "`n[6/10] 查看 WSL 分发版..." -ForegroundColor Yellow
wsl --list -v

# 导出
Write-Host "`n[7/10] 导出 docker-desktop-data (需要几分钟，请耐心等待)..." -ForegroundColor Yellow
$exportPath = Join-Path $TempExport "docker-desktop-data.tar"
wsl --export docker-desktop-data $exportPath 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   导出成功" -ForegroundColor Green
} else {
    Write-Host "   导出失败 (错误码: $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "   可能 docker-desktop-data 不存在，尝试导出 docker-desktop..." -ForegroundColor Yellow
    wsl --export docker-desktop $exportPath 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   导出 docker-desktop 也失败！" -ForegroundColor Red
        exit 1
    }
}

# 注销
Write-Host "`n[8/10] 注销旧的分发版..." -ForegroundColor Yellow
wsl --unregister docker-desktop-data 2>&1 | Out-Null
Write-Host "   完成" -ForegroundColor Green

# 导入
Write-Host "`n[9/10] 导入到新位置 (需要几分钟，请耐心等待)..." -ForegroundColor Yellow
wsl --import docker-desktop-data $TargetLocation $exportPath --version 2 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   导入成功" -ForegroundColor Green
} else {
    Write-Host "   导入失败 (错误码: $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

# 清理
Write-Host "`n[10/10] 清理临时文件..." -ForegroundColor Yellow
if (Test-Path $exportPath) {
    Remove-Item $exportPath -Force
}
if (Test-Path $TempExport) {
    Remove-Item $TempExport -Recurse -Force
}
Write-Host "   完成" -ForegroundColor Green

# 验证
Write-Host "`n验证新位置..." -ForegroundColor Yellow
wsl --list -v
Write-Host ""

$newVhdx = Get-ChildItem -Path $TargetLocation -Filter "*.vhdx" -Recurse -ErrorAction SilentlyContinue
if ($newVhdx) {
    foreach ($file in $newVhdx) {
        $sizeGB = [math]::Round($file.Length/1GB, 2)
        Write-Host "   新位置文件: $($file.FullName)" -ForegroundColor Green
        Write-Host "   大小: $sizeGB GB" -ForegroundColor Green
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "✓ 迁移完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "新位置: $TargetLocation" -ForegroundColor Green
Write-Host "`n下一步:" -ForegroundColor Yellow
Write-Host "1. 启动 Docker Desktop" -ForegroundColor White
Write-Host "2. 检查 Docker 是否正常工作" -ForegroundColor White
Write-Host "3. 如果一切正常，可以手动删除旧文件:" -ForegroundColor White
Write-Host "   C:\Users\wing\AppData\Local\Docker\wsl\disk" -ForegroundColor Gray



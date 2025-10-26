# Docker Desktop 数据迁移脚本
# 将 Docker 数据从 C 盘迁移到其他盘

param(
    [string]$TargetDrive = "D:",
    [string]$TargetPath = "docker"
)

$NewLocation = Join-Path $TargetDrive $TargetPath
$TempExport = Join-Path $TargetDrive "temp_docker_export"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker Desktop 数据迁移工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "当前位置: C:\Users\wing\AppData\Local\Docker\wsl\disk" -ForegroundColor Yellow
Write-Host "目标位置: $NewLocation" -ForegroundColor Green
Write-Host ""

# 检查当前 Docker 数据大小
Write-Host "1. 检查当前数据大小..." -ForegroundColor Yellow
$currentVhdx = Get-ChildItem -Path "C:\Users\wing\AppData\Local\Docker\wsl\disk" -Filter "*.vhdx" -ErrorAction SilentlyContinue
if ($currentVhdx) {
    foreach ($file in $currentVhdx) {
        $sizeGB = [math]::Round($file.Length/1GB, 2)
        Write-Host "   发现: $($file.Name) - $sizeGB GB" -ForegroundColor White
    }
} else {
    Write-Host "   未找到 vhdx 文件" -ForegroundColor Red
}

# 检查目标盘空间
Write-Host "`n2. 检查目标磁盘空间..." -ForegroundColor Yellow
$drive = Get-PSDrive -Name $TargetDrive.TrimEnd(':') -ErrorAction SilentlyContinue
if ($drive) {
    $freeSpaceGB = [math]::Round($drive.Free/1GB, 2)
    Write-Host "   $TargetDrive 可用空间: $freeSpaceGB GB" -ForegroundColor White
} else {
    Write-Host "   警告: 目标驱动器 $TargetDrive 不存在！" -ForegroundColor Red
    exit 1
}

Write-Host "`n准备迁移到: $NewLocation" -ForegroundColor Cyan
$confirm = Read-Host "是否继续？(y/n)"
if ($confirm -ne 'y') {
    Write-Host "已取消" -ForegroundColor Yellow
    exit 0
}

# 创建目录
Write-Host "`n3. 创建目标目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $NewLocation | Out-Null
New-Item -ItemType Directory -Force -Path $TempExport | Out-Null
Write-Host "   完成" -ForegroundColor Green

# 停止 Docker
Write-Host "`n4. 停止 Docker Desktop 和 WSL..." -ForegroundColor Yellow
Write-Host "   请手动退出 Docker Desktop (右键托盘图标 -> Quit Docker Desktop)" -ForegroundColor Cyan
Write-Host "   然后按任意键继续..."
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')

wsl --shutdown
Start-Sleep -Seconds 5
Write-Host "   WSL 已关闭" -ForegroundColor Green

# 查看 WSL 分发版
Write-Host "`n5. 查看 WSL 分发版..." -ForegroundColor Yellow
wsl --list -v

# 导出 docker-desktop-data
Write-Host "`n6. 导出 docker-desktop-data (这可能需要几分钟)..." -ForegroundColor Yellow
$exportPath = Join-Path $TempExport "docker-desktop-data.tar"
wsl --export docker-desktop-data $exportPath
if ($LASTEXITCODE -eq 0) {
    Write-Host "   导出成功" -ForegroundColor Green
} else {
    Write-Host "   导出失败！" -ForegroundColor Red
    exit 1
}

# 注销旧的分发版
Write-Host "`n7. 注销旧的分发版..." -ForegroundColor Yellow
wsl --unregister docker-desktop-data
if ($LASTEXITCODE -eq 0) {
    Write-Host "   注销成功" -ForegroundColor Green
} else {
    Write-Host "   注销失败！" -ForegroundColor Red
    exit 1
}

# 导入到新位置
Write-Host "`n8. 导入到新位置 (这可能需要几分钟)..." -ForegroundColor Yellow
$dataPath = Join-Path $NewLocation "data"
wsl --import docker-desktop-data $dataPath $exportPath --version 2
if ($LASTEXITCODE -eq 0) {
    Write-Host "   导入成功" -ForegroundColor Green
} else {
    Write-Host "   导入失败！" -ForegroundColor Red
    exit 1
}

# 清理临时文件
Write-Host "`n9. 清理临时文件..." -ForegroundColor Yellow
Remove-Item $exportPath -Force
Remove-Item $TempExport -Force
Write-Host "   完成" -ForegroundColor Green

# 验证
Write-Host "`n10. 验证新位置..." -ForegroundColor Yellow
wsl --list -v
$newVhdx = Get-ChildItem -Path $dataPath -Filter "*.vhdx" -Recurse -ErrorAction SilentlyContinue
if ($newVhdx) {
    foreach ($file in $newVhdx) {
        $sizeGB = [math]::Round($file.Length/1GB, 2)
        Write-Host "   发现: $($file.FullName) - $sizeGB GB" -ForegroundColor Green
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "迁移完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "新位置: $NewLocation\data" -ForegroundColor Green
Write-Host "现在可以启动 Docker Desktop 了" -ForegroundColor Yellow
Write-Host ""
Write-Host "提示: 如果 Docker 运行正常，可以删除旧的 vhdx 文件：" -ForegroundColor Cyan
Write-Host "C:\Users\wing\AppData\Local\Docker\wsl\disk" -ForegroundColor White



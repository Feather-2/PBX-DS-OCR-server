# Docker Desktop VHDX 文件迁移脚本
# 将 docker_data.vhdx 从 C 盘迁移到 G:\dockerfile

$SourcePath = "C:\Users\wing\AppData\Local\Docker\wsl"
$TargetPath = "G:\dockerfile\wsl"
$BackupPath = "C:\Users\wing\AppData\Local\Docker\wsl.backup"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker VHDX 文件迁移到 G:\dockerfile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 检查是否以管理员权限运行
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "错误: 必须以管理员权限运行此脚本！" -ForegroundColor Red
    Write-Host "请右键 PowerShell -> 以管理员身份运行" -ForegroundColor Yellow
    exit 1
}

# 检查源文件
Write-Host "`n[1/9] 检查源文件..." -ForegroundColor Yellow
if (Test-Path $SourcePath) {
    $vhdxFiles = Get-ChildItem $SourcePath -Recurse -Filter "*.vhdx"
    foreach ($file in $vhdxFiles) {
        $sizeGB = [math]::Round($file.Length/1GB, 2)
        Write-Host "   $($file.Name): $sizeGB GB" -ForegroundColor White
    }
} else {
    Write-Host "   错误: 源路径不存在！" -ForegroundColor Red
    exit 1
}

# 检查目标盘空间
Write-Host "`n[2/9] 检查 G 盘空间..." -ForegroundColor Yellow
$drive = Get-PSDrive -Name "G" -ErrorAction SilentlyContinue
if ($drive) {
    $freeSpaceGB = [math]::Round($drive.Free/1GB, 2)
    Write-Host "   可用空间: $freeSpaceGB GB" -ForegroundColor White
    if ($freeSpaceGB -lt 20) {
        Write-Host "   警告: 空间可能不足！" -ForegroundColor Red
    }
} else {
    Write-Host "   错误: G 盘不存在！" -ForegroundColor Red
    exit 1
}

# 提示关闭 Docker
Write-Host "`n[3/9] 请关闭 Docker Desktop..." -ForegroundColor Yellow
Write-Host "   1. 右键托盘的 Docker 图标" -ForegroundColor Cyan
Write-Host "   2. 点击 'Quit Docker Desktop'" -ForegroundColor Cyan
Write-Host "   3. 等待完全退出后，按回车继续..." -ForegroundColor Cyan
Read-Host

# 关闭 WSL
Write-Host "`n[4/9] 关闭 WSL..." -ForegroundColor Yellow
wsl --shutdown
Start-Sleep -Seconds 3
Write-Host "   完成" -ForegroundColor Green

# 创建目标目录
Write-Host "`n[5/9] 创建目标目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
Write-Host "   完成" -ForegroundColor Green

# 复制文件
Write-Host "`n[6/9] 复制文件到新位置 (需要几分钟，约 17 GB)..." -ForegroundColor Yellow
Write-Host "   源: $SourcePath" -ForegroundColor Gray
Write-Host "   目标: $TargetPath" -ForegroundColor Gray
try {
    Copy-Item -Path "$SourcePath\*" -Destination $TargetPath -Recurse -Force
    Write-Host "   复制成功" -ForegroundColor Green
} catch {
    Write-Host "   复制失败: $_" -ForegroundColor Red
    exit 1
}

# 验证复制
Write-Host "`n[7/9] 验证新位置文件..." -ForegroundColor Yellow
$newVhdx = Get-ChildItem $TargetPath -Recurse -Filter "*.vhdx"
if ($newVhdx) {
    foreach ($file in $newVhdx) {
        $sizeGB = [math]::Round($file.Length/1GB, 2)
        Write-Host "   ✓ $($file.Name): $sizeGB GB" -ForegroundColor Green
    }
} else {
    Write-Host "   错误: 新位置没有找到 vhdx 文件！" -ForegroundColor Red
    exit 1
}

# 重命名旧目录为备份
Write-Host "`n[8/9] 备份旧目录..." -ForegroundColor Yellow
if (Test-Path $BackupPath) {
    Write-Host "   备份已存在，跳过..." -ForegroundColor Yellow
} else {
    Rename-Item $SourcePath $BackupPath
    Write-Host "   完成" -ForegroundColor Green
}

# 创建符号链接
Write-Host "`n[9/9] 创建符号链接..." -ForegroundColor Yellow
try {
    New-Item -ItemType SymbolicLink -Path $SourcePath -Target $TargetPath -Force | Out-Null
    Write-Host "   完成" -ForegroundColor Green
} catch {
    Write-Host "   创建符号链接失败: $_" -ForegroundColor Red
    Write-Host "   正在恢复备份..." -ForegroundColor Yellow
    if (Test-Path $BackupPath) {
        Rename-Item $BackupPath $SourcePath
    }
    exit 1
}

# 完成
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "✓ 迁移完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`n数据已迁移到: $TargetPath" -ForegroundColor Green
Write-Host "符号链接已创建: $SourcePath -> $TargetPath" -ForegroundColor Green
Write-Host "`n下一步:" -ForegroundColor Yellow
Write-Host "1. 启动 Docker Desktop" -ForegroundColor White
Write-Host "2. 运行一些容器测试是否正常" -ForegroundColor White
Write-Host "3. 确认无误后，可删除备份:" -ForegroundColor White
Write-Host "   Remove-Item '$BackupPath' -Recurse -Force" -ForegroundColor Gray
Write-Host "`n备份位置: $BackupPath" -ForegroundColor Cyan



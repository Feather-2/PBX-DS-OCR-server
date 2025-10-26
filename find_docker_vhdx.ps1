# 查找 Docker VHDX 文件的位置和大小
Write-Host "=== 查找 Docker VHDX 文件 ===" -ForegroundColor Cyan

# 1. 检查 LocalAppData\Docker
Write-Host "`n1. 检查 Docker Desktop 数据目录..." -ForegroundColor Yellow
$dockerPath = "$env:LOCALAPPDATA\Docker"
if (Test-Path $dockerPath) {
    Get-ChildItem -Path $dockerPath -Recurse -Filter "*.vhdx" -ErrorAction SilentlyContinue | 
        ForEach-Object {
            [PSCustomObject]@{
                Location = $_.FullName
                'Size (GB)' = [math]::Round($_.Length/1GB, 2)
                'Size (MB)' = [math]::Round($_.Length/1MB, 2)
            }
        } | Format-Table -AutoSize
}

# 2. 检查 WSL 相关目录
Write-Host "`n2. 检查 WSL 分发版..." -ForegroundColor Yellow
wsl --list -v

# 3. 检查所有用户目录下的 Docker 相关 vhdx
Write-Host "`n3. 搜索所有 Docker 相关的 vhdx 文件..." -ForegroundColor Yellow
Get-ChildItem -Path $env:USERPROFILE -Recurse -Filter "*.vhdx" -ErrorAction SilentlyContinue | 
    Where-Object { $_.Name -like "*docker*" } |
    ForEach-Object {
        [PSCustomObject]@{
            Location = $_.FullName
            'Size (GB)' = [math]::Round($_.Length/1GB, 2)
        }
    } | Format-Table -AutoSize

# 4. 检查 LocalAppData\Packages (WSL)
Write-Host "`n4. 检查 Packages 目录..." -ForegroundColor Yellow
$packagesPath = "$env:LOCALAPPDATA\Packages"
if (Test-Path $packagesPath) {
    Get-ChildItem -Path $packagesPath -Recurse -Filter "ext4.vhdx" -ErrorAction SilentlyContinue | 
        Where-Object { $_.DirectoryName -like "*docker*" } |
        ForEach-Object {
            [PSCustomObject]@{
                Location = $_.FullName
                'Size (GB)' = [math]::Round($_.Length/1GB, 2)
            }
        } | Format-Table -AutoSize
}

Write-Host "`n=== 搜索完成 ===" -ForegroundColor Green



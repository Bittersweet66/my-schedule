# 我的日程 · 安装包构建脚本
# 用法：pwsh -File installer/build.ps1 [-Version 1.1.0] [-PythonRoot <Python安装目录>]
#
# 产物：
#   dist\我的日程_安装包_v<版本>.exe   单文件安装程序（内置 Python 运行时）
#   dist\我的日程_便携版_v<版本>.zip   解压即用的绿色版

param(
    [string]$Version = "1.1.0",
    [string]$PythonRoot = ""
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$installerDir = Join-Path $root 'installer'
$build = Join-Path $root 'build'
$payload = Join-Path $build 'payload'
$dist = Join-Path $root 'dist'
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$icon = Join-Path $root 'assets\icon.ico'
$payloadZip = Join-Path $build 'payload.zip'
$setupExe = Join-Path $build 'setup.exe'
$uninstallExe = Join-Path $build 'uninstall.exe'

function Write-Step($text) { Write-Host ""; Write-Host ("== " + $text) -ForegroundColor Cyan }
function Get-Bytes($path) { return (Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum }

if (-not (Test-Path $csc)) { throw "找不到 csc.exe：$csc" }
if (-not (Test-Path $icon)) { throw "找不到图标：$icon（先运行 tools/make_icon.py）" }

# 自动探测 Python 安装目录（也可用 -PythonRoot 手动指定）
if ([string]::IsNullOrWhiteSpace($PythonRoot)) {
    $pythonExe = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonExe) { throw "未找到 python。请安装 Python 3，或用 -PythonRoot 指定安装目录。" }
    $PythonRoot = (& $pythonExe.Source -c "import sys; print(sys.base_prefix)" 2>$null | Select-Object -First 1)
    if ($PythonRoot) { $PythonRoot = $PythonRoot.Trim() }
}
if (-not $PythonRoot -or -not (Test-Path $PythonRoot)) { throw "Python 安装目录无效：$PythonRoot" }
Write-Host ("  Python: " + $PythonRoot)

# ---------------------------------------------------------------- 1. 清理
Write-Step "清理构建目录"
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force -Path $payload | Out-Null
New-Item -ItemType Directory -Force -Path $dist | Out-Null

# ---------------------------------------------------------------- 2. 应用文件
Write-Step "收集应用文件"
Copy-Item (Join-Path $root 'backend') (Join-Path $payload 'backend') -Recurse
Copy-Item (Join-Path $root 'web') (Join-Path $payload 'web') -Recurse
Copy-Item (Join-Path $root 'assets') (Join-Path $payload 'assets') -Recurse
Copy-Item (Join-Path $root '启动日程软件.vbs') $payload
Copy-Item (Join-Path $root '调试启动.bat') $payload
Copy-Item (Join-Path $root 'README.md') $payload
# 说明：项目 docs/ 里的截图留在仓库中，不进安装包
Get-ChildItem $payload -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Get-ChildItem $payload -Recurse -Include '*.pyc','*.log' | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host ("  应用文件：{0:N1} MB" -f ((Get-Bytes $payload) / 1MB))

# ---------------------------------------------------------------- 3. Python 运行时
Write-Step "复制并裁剪 Python 运行时"
$runtime = Join-Path $payload 'runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

$coreFiles = @('python.exe', 'pythonw.exe', 'python311.dll', 'python3.dll',
               'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt')
foreach ($file in $coreFiles) {
    $source = Join-Path $PythonRoot $file
    if (Test-Path $source) { Copy-Item $source $runtime }
}
Copy-Item (Join-Path $PythonRoot 'DLLs') $runtime -Recurse
Copy-Item (Join-Path $PythonRoot 'tcl') $runtime -Recurse

$excludeDirs = 'site-packages', 'test', 'ensurepip', 'idlelib', 'pydoc_data', 'lib2to3',
               'distutils', 'wsgiref', 'xmlrpc', 'curses', 'dbm', 'venv'
robocopy (Join-Path $PythonRoot 'Lib') (Join-Path $runtime 'Lib') /E /XD $excludeDirs /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy 复制 Python 标准库失败（exit=$LASTEXITCODE）" }

# 运行时自检：确认裁剪后仍能加载应用所需模块
$probe = Join-Path $runtime 'python.exe'
$probeCode = "import sys, json, http.server, urllib.request, subprocess, threading, datetime, pathlib, mimetypes, tkinter; print('runtime-ok', sys.version.split()[0])"
$probeOutput = & $probe -c $probeCode 2>&1
if ($LASTEXITCODE -ne 0 -or ($probeOutput -join ' ') -notmatch 'runtime-ok') {
    throw "运行时自检失败：$probeOutput"
}
Write-Host ("  运行时：{0:N1} MB  ({1})" -f ((Get-Bytes $runtime) / 1MB), ($probeOutput -join ' '))

# ---------------------------------------------------------------- 4. 便携版（不含卸载程序）
Write-Step "生成便携版 zip"
$portableZip = Join-Path $build 'portable.zip'
if (Test-Path $portableZip) { Remove-Item $portableZip -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $payload, $portableZip,
    [System.IO.Compression.CompressionLevel]::Optimal, $false)
Write-Host ("  portable.zip：{0:N1} MB" -f ((Get-Item $portableZip).Length / 1MB))

# ---------------------------------------------------------------- 5. 卸载程序
Write-Step "编译 uninstall.exe"
& $csc /nologo /target:winexe /optimize+ /out:$uninstallExe /win32icon:$icon `
    /reference:System.dll /reference:System.Core.dll /reference:System.Windows.Forms.dll `
    /reference:System.Drawing.dll /reference:System.IO.Compression.dll `
    (Join-Path $installerDir 'uninstall.cs')
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $uninstallExe)) { throw "编译 uninstall.exe 失败" }
Copy-Item $uninstallExe $payload
Write-Host ("  uninstall.exe：{0:N0} KB" -f ((Get-Item $uninstallExe).Length / 1KB))

# ---------------------------------------------------------------- 6. 打包安装载荷
Write-Step "生成 payload.zip"
if (Test-Path $payloadZip) { Remove-Item $payloadZip -Force }
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $payload, $payloadZip,
    [System.IO.Compression.CompressionLevel]::Optimal, $false)
Write-Host ("  payload.zip：{0:N1} MB" -f ((Get-Item $payloadZip).Length / 1MB))

# ---------------------------------------------------------------- 7. 编译安装程序
Write-Step "编译 setup.exe（内嵌载荷）"
& $csc /nologo /target:winexe /optimize+ /out:$setupExe /win32icon:$icon `
    "/resource:$payloadZip,payload.zip" `
    /reference:System.dll /reference:System.Core.dll /reference:System.Windows.Forms.dll `
    /reference:System.Drawing.dll /reference:System.IO.Compression.dll `
    /reference:System.IO.Compression.FileSystem.dll `
    (Join-Path $installerDir 'setup.cs')
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $setupExe)) { throw "编译 setup.exe 失败" }
Write-Host ("  setup.exe：{0:N1} MB" -f ((Get-Item $setupExe).Length / 1MB))

# ---------------------------------------------------------------- 8. 输出到 dist
Write-Step "输出发布文件"
$setupName = "我的日程_安装包_v$Version.exe"
$portableName = "我的日程_便携版_v$Version.zip"
Copy-Item $setupExe (Join-Path $dist $setupName) -Force
Copy-Item $portableZip (Join-Path $dist $portableName) -Force

Write-Host ""
Write-Host "构建完成：" -ForegroundColor Green
Get-ChildItem $dist -Filter "*v$Version.*" | ForEach-Object {
    Write-Host ("  {0}  ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB))
}
Write-Host ""

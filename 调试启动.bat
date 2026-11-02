@echo off
chcp 65001 >nul
title 我的日程 · 调试模式
cd /d "%~dp0"

set "PY=%~dp0runtime\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "%~dp0backend\app.py" (
  echo 找不到程序文件。
  pause
  exit /b 1
)

echo ============================================
echo   我的日程 - 调试模式（关闭窗口即退出）
echo   解释器: %PY%
echo ============================================
echo.
"%PY%" "%~dp0backend\app.py" %*
echo.
echo 服务已结束，按任意键关闭窗口。
pause >nul

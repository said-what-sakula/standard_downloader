@echo off
chcp 65001 >nul
title 构建前端

echo [前端] 安装依赖...
cd frontend
npm install
if errorlevel 1 (
    echo [错误] npm install 失败
    pause
    exit /b 1
)

echo [前端] 构建生产版本...
npm run build
if errorlevel 1 (
    echo [错误] 构建失败
    pause
    exit /b 1
)

echo.
echo ✅ 前端构建完成，产物在 frontend/dist/
echo    启动 start.bat 后访问 http://127.0.0.1:8000
pause

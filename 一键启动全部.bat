@echo off
chcp 65001 >nul
title 大肥鱼 - 一键启动全部
cd /d "%~dp0"

REM 弹幕监听需要管理员权限（安装证书、设置系统代理），这里先自提权
net session >nul 2>&1
if errorlevel 1 (
    echo 需要管理员权限，正在请求提权，请在弹窗中点"是"...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start-dafeiyu.ps1"

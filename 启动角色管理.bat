@echo off
chcp 65001 >nul
title 大肥鱼 - 角色管理
cd /d "%~dp0"
echo ========================================================
echo   角色管理页: http://127.0.0.1:8090
echo   切皮套 / 换音色 / 改人设 / 保存角色档案
echo ========================================================
.venv\Scripts\python.exe tools\character_manager.py
pause

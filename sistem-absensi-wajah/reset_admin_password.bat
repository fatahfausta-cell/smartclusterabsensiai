@echo off
chcp 65001 >nul
title Reset Password Admin - Absensi Wajah
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv tidak ditemukan.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" reset_admin.py
pause

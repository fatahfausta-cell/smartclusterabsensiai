@echo off
chcp 65001 >nul
title Mematikan Sistem Absensi Wajah
echo Mencari server di port 5050...
set DITEMUKAN=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5050 ^| findstr LISTENING') do (
  taskkill /PID %%a /F >nul 2>&1
  set DITEMUKAN=1
)
if "%DITEMUKAN%"=="1" (
  echo Server absensi sudah DIMATIKAN.
) else (
  echo Tidak ada server yang berjalan di port 5050.
)
timeout /t 3 >nul

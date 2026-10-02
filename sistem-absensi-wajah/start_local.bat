@echo off
chcp 65001 >nul
title Sistem Absensi Wajah - JANGAN DITUTUP
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment .venv tidak ditemukan.
  echo Jalankan SEKALI saja perintah berikut di folder ini:
  echo    python -m venv .venv
  echo    .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

echo ============================================================
echo   SISTEM ABSENSI WAJAH - MODE LOKAL
echo ------------------------------------------------------------
echo   - Biarkan jendela ini TERBUKA selama sistem dipakai.
echo   - Browser akan terbuka otomatis di http://localhost:5050
echo     (tunggu +- 15 detik, model AI sedang dimuat).
echo   - Untuk mematikan: tutup jendela ini atau tekan Ctrl+C.
echo ============================================================
echo.

rem buka browser otomatis setelah server siap (+- 15 detik)
start "" cmd /c "timeout /t 15 >nul & start http://localhost:5050"

".venv\Scripts\python.exe" app.py
echo.
echo Server berhenti.
pause

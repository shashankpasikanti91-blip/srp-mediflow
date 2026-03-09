@echo off
chcp 65001 > nul
title SRP MediFlow HMS v4 - Hospital Management System
color 0A
set PYTHONIOENCODING=utf-8
echo.
echo ============================================================
echo   SRP MediFlow Hospital Management System
echo   Version 4.0 - Full HMS (OPD+IPD+Pharmacy+Lab+Analytics)
echo ============================================================
echo.
echo Starting SRP MediFlow HMS v4 server...
echo Local:  http://localhost:7500
echo Admin:  http://localhost:7500/admin
echo.
cd /d "%~dp0"
C:\Python314\python.exe -X utf8 srp_mediflow_server.py
pause

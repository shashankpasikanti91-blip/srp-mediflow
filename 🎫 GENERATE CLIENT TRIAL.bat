@echo off
chcp 65001 > nul
title SRP MediFlow - Generate Client Trial Access
color 0B
echo.
echo ============================================================
echo   SRP MediFlow HMS v4 - Client Trial Generator
echo   Creates a 7-day trial access card for your client
echo ============================================================
echo.
set /p HOSPITAL_NAME="Enter Hospital / Client Name: "
set /p TRIAL_DAYS="Trial Days (press Enter for 7): "
if "%TRIAL_DAYS%"=="" set TRIAL_DAYS=7
echo.
echo Generating trial access card...
echo.
cd /d "%~dp0"
C:\Python314\python.exe -X utf8 generate_client_trial.py --hospital "%HOSPITAL_NAME%" --days %TRIAL_DAYS%
echo.
pause

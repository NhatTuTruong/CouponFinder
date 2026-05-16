@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Chay truoc: python -m venv .venv
    echo            .\.venv\Scripts\python.exe -m pip install -e ".[build-exe]"
    exit /b 1
)

taskkill /IM CouponFinder.exe /F >nul 2>&1

".venv\Scripts\python.exe" -m pip install -q -e ".[build-exe]"
".venv\Scripts\python.exe" -m coupon_finder.cli build-exe
exit /b %ERRORLEVEL%

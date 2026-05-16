# Đóng gói Coupon Finder thành app .exe
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Chạy trước: python -m venv .venv && pip install -e .[build-exe]"
    exit 1
}

taskkill /IM CouponFinder.exe /F 2>$null | Out-Null

.\.venv\Scripts\python.exe -m pip install -q -e ".[build-exe]"
.\.venv\Scripts\python.exe -m coupon_finder.cli build-exe

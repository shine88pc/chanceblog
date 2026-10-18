@echo off
title Chance_Blog Git Auto Synchronizer
echo ===================================================
echo  Chance_Blog Realtime Git Auto Sync Engine Running...
echo ===================================================

:loop
:: 1. 원격 저장소 변경사항 자동 가져오기 (GitHub/Copilot/Actions 수정한 내용)
git fetch origin main >nul 2>&1
git pull origin main --rebase >nul 2>&1

:: 2. 로컬에서 수정된 파일이 있다면 자동으로 커밋 & 푸시
git status --porcelain | findstr /R "^." >nul 2>&1
if %errorlevel% equ 0 (
    echo [%time%] Local changes detected. Auto pushing to GitHub...
    git add .
    git commit -m "🤖 Auto Sync: Local edits synchronized"
    git push origin main
    echo [%time%] Push completed!
)

:: 30초마다 자동으로 동기화 상태 체크
timeout /t 30 /nobreak >nul
goto loop
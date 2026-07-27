@echo off
REM Naver listing collector launcher (for Windows Task Scheduler).
REM Must run on a residential IP (this PC). Collects, then commits/pushes.
REM Log: naver_run.log

cd /d "%~dp0"

echo ================================================= >> naver_run.log
echo [%date% %time%] collect start >> naver_run.log

python naver_collect.py >> naver_run.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] [ERROR] collect failed - skip commit >> naver_run.log
  exit /b 1
)

REM sync remote first (avoid conflicts with Actions commits)
git pull --rebase --autostash >> naver_run.log 2>&1

git add naver_snapshot.json naver_events.json >> naver_run.log 2>&1
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "chore: naver listing snapshot %date%" >> naver_run.log 2>&1
  git push >> naver_run.log 2>&1
  echo [%date% %time%] commit/push done >> naver_run.log
) else (
  echo [%date% %time%] no change - skip commit >> naver_run.log
)

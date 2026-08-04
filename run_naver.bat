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

REM Commit local collector output FIRST. This PC is the sole author of these
REM two files, so on any merge conflict we keep OUR local version (-X ours).
REM (Old flow used `pull --rebase --autostash`, which corrupted naver_events.json
REM  with conflict markers whenever the remote had new commits.)
git add naver_snapshot.json naver_events.json naver_sold_history.json >> naver_run.log 2>&1
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "chore: naver listing snapshot %date%" >> naver_run.log 2>&1

  REM Merge remote (Actions commits index.html, apt_state.json, ...) keeping
  REM our local snapshot/events on conflict. No rebase => no autostash step.
  git pull --no-rebase --no-edit -X ours >> naver_run.log 2>&1

  git push >> naver_run.log 2>&1
  if errorlevel 1 (
    echo [%date% %time%] push failed - retry after re-pull >> naver_run.log
    git pull --no-rebase --no-edit -X ours >> naver_run.log 2>&1
    git push >> naver_run.log 2>&1
  )
  echo [%date% %time%] commit/push done >> naver_run.log
) else (
  echo [%date% %time%] no change - skip commit >> naver_run.log
)

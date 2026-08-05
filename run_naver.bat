@echo off
REM Local collector launcher (for Windows Task Scheduler).
REM Must run on a residential IP (this PC): naver AND data.go.kr both block
REM datacenter/overseas IPs, so GitHub Actions cannot fetch them. Collects here,
REM then commits/pushes. GitHub Actions only sends Telegram + builds dashboard.
REM Log: naver_run.log

cd /d "%~dp0"

echo ================================================= >> naver_run.log
echo [%date% %time%] collect start >> naver_run.log

python naver_collect.py >> naver_run.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] [ERROR] naver collect failed - continue with apt >> naver_run.log
)

REM Apt real-transactions (data.go.kr) — also blocked overseas, collect locally.
REM Writes apt_state.json / search_data.json / reported_dates.json /
REM building_cache.json / apt_events.json. Key is read from datago_key.txt.
echo [%date% %time%] apt collect start >> naver_run.log
set MB_MODE=collect
python bot.py >> naver_run.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] [WARN] apt collect failed - commit naver only >> naver_run.log
)
set MB_MODE=

REM Commit local collector output FIRST. This PC is the sole author of these
REM files, so on any merge conflict we keep OUR local version (-X ours).
REM (Old flow used `pull --rebase --autostash`, which corrupted naver_events.json
REM  with conflict markers whenever the remote had new commits.)
git add naver_snapshot.json naver_events.json naver_sold_history.json apt_state.json search_data.json reported_dates.json building_cache.json apt_events.json >> naver_run.log 2>&1
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "chore: local collect (naver+apt) %date%" >> naver_run.log 2>&1

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

@echo off
REM ── 네이버 매물 수집 로컬 런처 (Windows 작업 스케줄러용) ──
REM   반드시 가정용 IP(이 PC)에서 실행. 수집 후 스냅샷/이벤트 커밋·푸시.
REM   실행 로그: naver_run.log (최근 실행 기록 확인용)

cd /d "%~dp0"

echo ================================================= >> naver_run.log
echo [%date% %time%] 수집 시작 >> naver_run.log

python naver_collect.py >> naver_run.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] [ERROR] 수집 실패 - 커밋 생략 >> naver_run.log
  exit /b 1
)

REM 최신 원격 반영 후 커밋 (Actions가 커밋한 index.html 등과 충돌 방지)
git pull --rebase --autostash >> naver_run.log 2>&1

git add naver_snapshot.json naver_events.json >> naver_run.log 2>&1
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "chore: 네이버 매물 스냅샷 %date%" >> naver_run.log 2>&1
  git push >> naver_run.log 2>&1
  echo [%date% %time%] 커밋/푸시 완료 >> naver_run.log
) else (
  echo [%date% %time%] 변동 없음 - 커밋 생략 >> naver_run.log
)
